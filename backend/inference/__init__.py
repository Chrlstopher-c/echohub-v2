"""Domaine `inference` — décider d'un plan de chargement, l'appliquer, générer.

Interface publique du domaine. Deux surfaces distinctes, à ne pas confondre :

- le **planificateur** (`planifier`, `degrader`) est pur : il décide à partir de mesures qu'on lui
  donne, ne touche ni GPU ni disque, et se teste sans matériel. C'est ce qui rend ses règles
  vérifiables, contrairement à la v1 où elles étaient dispersées dans le chargeur ;
- le **superviseur** applique : il charge, sonde, génère, décharge.

`creer_moteur_chat` est la fabrique que le domaine `chat` cherche à l'exécution. Elle est ici, et
non dans `chat`, parce que c'est le domaine qui possède le moteur qui doit fournir l'adaptateur —
`chat` ne connaît que la forme qu'il attend (`chat/port_inference.py`), jamais notre implémentation.

Aucun import de `backend.chat` dans ce fichier : la dépendance ne va que dans un sens. La requête
reçue est lue par attributs et le flux rendu sous une forme que `chat.adaptation_inference` sait
normaliser — c'est exactement le point de souplesse que ce module documente.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from backend.inference.engines_adapters import (
    MessageChat,
    OptionsGeneration,
    superviseur,
)
from backend.inference.planner import (
    DemandeDeChargement,
    MetadonneesModele,
    PlanDeChargement,
    PreferencesUtilisateur,
    ProfilMachine,
    degrader,
    planifier,
)


def _options_depuis(parametres: object) -> OptionsGeneration:
    """Traduit les réglages d'une conversation en options moteur.

    Lecture par attributs plutôt qu'import du modèle de `chat` : la traduction est explicite et
    la dépendance reste à sens unique. Un champ absent retombe sur le défaut du moteur, jamais sur
    une valeur inventée ici.
    """

    def champ(nom: str) -> Any:
        return getattr(parametres, nom, None)

    top_k = champ("top_k")
    return OptionsGeneration(
        temperature=champ("temperature") if champ("temperature") is not None else 0.7,
        top_p=champ("top_p") if champ("top_p") is not None else 0.95,
        # `0` signifie « désactivé » côté llama.cpp, alors que le contrat moteur exige `>= 1` ou
        # `None`. Les deux disent la même chose ; on traduit plutôt que de laisser passer un 0
        # qui serait refusé à la validation.
        top_k=top_k if isinstance(top_k, int) and top_k >= 1 else None,
        repetition_penalty=champ("penalite_repetition"),
        max_tokens=champ("max_tokens"),
        stop=list(champ("sequences_arret") or []),
        graine=champ("graine"),
    )


def _messages_depuis(messages: object) -> list[MessageChat]:
    """Convertit les messages de la conversation au format des moteurs (`content`, pas `contenu`)."""
    convertis: list[MessageChat] = []
    for message in messages or ():
        role = getattr(message, "role", None)
        contenu = getattr(message, "contenu", None)
        if contenu is None:
            contenu = getattr(message, "content", None)
        if role is None or contenu is None:
            logger.warning("Message ignoré, forme inattendue : {}", type(message).__name__)
            continue
        convertis.append(MessageChat(role=role, content=contenu))
    return convertis


# Tours d'outils avant de rendre la main au modèle pour de bon. Un modèle peut légitimement
# enchaîner deux recherches ; au-delà, il boucle. La borne est là pour ça, et l'atteindre est
# journalisé — un plafond silencieux ressemblerait à une réponse normale.
TOURS_OUTILS_MAX = 3


def _texte_appel(appel: dict[str, Any]) -> tuple[str, Any]:
    """Nom et arguments d'un appel, quelle que soit la forme rendue par le gabarit du modèle."""
    fonction = appel.get("function")
    if isinstance(fonction, dict):
        return str(fonction.get("name", "")), fonction.get("arguments", "")
    return str(appel.get("name", "")), appel.get("arguments", "")


async def _resoudre_outils(
    messages: list[MessageChat],
    options: OptionsGeneration,
) -> list[MessageChat]:
    """Exécute les outils que le modèle demande, et rend la conversation enrichie des résultats.

    Le résultat d'un outil est réinjecté comme un tour d'assistant plutôt qu'avec le rôle `tool` :
    le contrat `MessageChat` du projet n'accepte que system/user/assistant, et les gabarits des
    modèles chargés ici lisent parfaitement un résultat annoncé en clair. Passer par un rôle que la
    moitié de la chaîne ne connaît pas aurait coûté une migration de contrat pour un gain nul.

    Tout échec ramène la conversation d'origine : le harnais ne doit jamais empêcher une réponse.
    """
    from backend.outils import executer, format_moteur

    outils = format_moteur()
    if not outils:
        return messages

    enrichis = list(messages)
    for tour in range(TOURS_OUTILS_MAX):
        try:
            appels = await superviseur.proposer_outils(enrichis, options, outils)
        except Exception as exc:  # noqa: BLE001 — frontière moteur : jamais fatale pour la réponse
            logger.warning("Proposition d'outils abandonnée au tour {} : {}", tour + 1, exc)
            return enrichis
        if not appels:
            return enrichis
        for appel in appels:
            nom, arguments = _texte_appel(appel)
            resultat = await executer(nom, arguments)
            etat = "résultat" if resultat.succes else "échec"
            enrichis.append(
                MessageChat(
                    role="assistant",
                    content=f"[outil {resultat.nom} — {etat}]\n{resultat.texte}",
                )
            )
    logger.warning("Borne de {} tours d'outils atteinte : la réponse suit avec ce qui a été trouvé.", TOURS_OUTILS_MAX)
    return enrichis


class MoteurChat:
    """Adaptateur du superviseur vers le port de génération de `chat`.

    Rend des dictionnaires — `{"texte": …}` puis `{"tokens_generes": …, "tokens_par_seconde": …}` —
    que `chat.adaptation_inference` normalise. Ce détour évite d'importer les modèles de `chat`
    ici, donc un cycle entre les deux domaines.
    """

    def generer(self, requete: object) -> AsyncIterator[dict[str, Any]]:
        """Ouvre le flux. Rend l'itérateur SANS être une coroutine, comme l'exige le port."""
        return self._flux(requete)

    async def _flux(self, requete: object) -> AsyncIterator[dict[str, Any]]:
        messages = _messages_depuis(getattr(requete, "messages", None))
        options = _options_depuis(getattr(requete, "parametres", None))
        messages = await _resoudre_outils(messages, options)
        debut = time.monotonic()
        tokens = 0

        async for morceau in superviseur.generer(messages, options):
            if morceau.type == "token" and morceau.contenu:
                tokens += 1
                yield {"texte": morceau.contenu}
            elif morceau.type == "erreur":
                # Le flux HTTP est déjà ouvert : signaler dans le flux est la seule façon d'informer.
                logger.error("Génération interrompue par le moteur : {}", morceau.contenu)
                raise RuntimeError(morceau.contenu or "Le moteur a interrompu la génération.")

        ecoule = time.monotonic() - debut
        # Le compte de tokens est celui des morceaux réellement reçus, et le débit en découle. Si
        # aucun token n'est passé, on rend `None` plutôt qu'un zéro qui ressemblerait à une mesure.
        yield {
            "tokens_generes": tokens or None,
            "tokens_par_seconde": (tokens / ecoule) if tokens and ecoule > 0 else None,
        }


def creer_moteur_chat() -> MoteurChat:
    """Fabrique cherchée par `chat.adaptation_inference` au premier besoin de génération."""
    return MoteurChat()


__all__ = [
    # Planification — pure, testable sans GPU
    "DemandeDeChargement",
    "MetadonneesModele",
    "PlanDeChargement",
    "PreferencesUtilisateur",
    "ProfilMachine",
    "planifier",
    "degrader",
    # Exécution
    "superviseur",
    "MessageChat",
    "OptionsGeneration",
    # Pont vers le domaine chat
    "MoteurChat",
    "creer_moteur_chat",
]
