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


"""Balises du flux annonçant un outil. Elles voyagent dans le texte de la réponse, comme celles du
raisonnement, et l'interface les replie de la même façon : l'utilisateur voit la recherche se
faire, sans que le résultat brut n'écrase la réponse.

Passer par le texte plutôt que par un type d'événement dédié n'est pas un raccourci : c'est ce qui
rend l'information PERSISTANTE. Un événement de flux disparaît au rechargement de la page, alors
qu'un message enregistré garde la trace de ce qui a été cherché — et c'est justement ce qui permet
de vérifier une réponse plus tard."""
BALISE_OUTIL_OUVRANTE = "<outil>"
BALISE_OUTIL_FERMANTE = "</outil>"


def _annonce(nom: str, arguments: object) -> str:
    """Ligne lisible d'un appel, montrée telle quelle dans le bloc replié."""
    if isinstance(arguments, dict):
        detail = ", ".join(f"{cle} : {valeur}" for cle, valeur in arguments.items())
    else:
        detail = str(arguments or "")
    return f"{nom}({detail})" if detail else nom


def _appels_demandes(texte: str) -> list[dict[str, Any]]:
    """Appels d'outils repérés dans ce que le modèle vient d'écrire.

    Lus dans le TEXTE reçu, parce que c'est là qu'ils arrivent : avec le gabarit natif d'un GGUF,
    llama-cpp-python ne remplit pas `tool_calls` et le modèle émet `<tool_call>{…}</tool_call>`
    au fil du flux. Le lire ici évite un second appel au moteur — qui construirait un prompt
    différent, perdrait le cache et doublerait le temps avant le premier token.
    """
    from backend.inference.engines_adapters.adaptateur_llama_cpp import _appels_dans_le_texte

    return _appels_dans_le_texte(texte)


async def _executer_appels(
    appels: list[dict[str, Any]],
    messages: list[MessageChat],
) -> AsyncIterator[dict[str, Any]]:
    """Exécute les appels demandés, en annonçant chacun dans le flux, et enrichit la conversation."""
    from backend.outils import executer

    for appel in appels:
        nom, arguments = _texte_appel(appel)
        yield {"texte": f"{BALISE_OUTIL_OUVRANTE}{_annonce(nom, arguments)}\n"}
        resultat = await executer(nom, arguments)
        etat = "résultat" if resultat.succes else "échec"
        yield {"texte": f"{resultat.texte}{BALISE_OUTIL_FERMANTE}\n\n"}
        messages.append(MessageChat(role="assistant", content=f"[outil {resultat.nom} — {etat}]\n{resultat.texte}"))


async def _resoudre_outils(
    messages: list[MessageChat],
    options: OptionsGeneration,
) -> AsyncIterator[dict[str, Any]]:
    """Exécute les outils demandés, en annonçant chaque étape dans le flux au fur et à mesure.

    Rend des fragments à afficher ET, en dernier lieu, la conversation enrichie sous la clé
    `messages` — l'appelant s'en sert pour la génération finale. Un générateur plutôt qu'une
    fonction : sans cela, l'utilisateur reste devant un écran figé pendant toute la recherche, sans
    savoir si quelque chose se passe.

    Le résultat d'un outil est réinjecté comme un tour d'assistant plutôt qu'avec le rôle `tool` :
    le contrat `MessageChat` du projet n'accepte que system/user/assistant, et les gabarits des
    modèles chargés ici lisent parfaitement un résultat annoncé en clair.

    Tout échec rend la conversation d'origine : le harnais ne doit jamais empêcher une réponse.
    """
    from backend.outils import executer, format_moteur

    outils = format_moteur()
    enrichis = list(messages)
    if not outils:
        yield {"messages": enrichis}
        return

    for tour in range(TOURS_OUTILS_MAX):
        try:
            appels = await superviseur.proposer_outils(enrichis, options, outils)
        except Exception as exc:  # noqa: BLE001 — frontière moteur : jamais fatale pour la réponse
            logger.warning("Proposition d'outils abandonnée au tour {} : {}", tour + 1, exc)
            break
        if not appels:
            break
        for appel in appels:
            nom, arguments = _texte_appel(appel)
            yield {"texte": f"{BALISE_OUTIL_OUVRANTE}{_annonce(nom, arguments)}\n"}
            resultat = await executer(nom, arguments)
            etat = "résultat" if resultat.succes else "échec"
            yield {"texte": f"{resultat.texte}{BALISE_OUTIL_FERMANTE}\n\n"}
            enrichis.append(MessageChat(role="assistant", content=f"[outil {resultat.nom} — {etat}]\n{resultat.texte}"))
    else:
        logger.warning("Borne de {} tours d'outils atteinte : la réponse suit avec ce qui existe.", TOURS_OUTILS_MAX)
    yield {"messages": enrichis}


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
        from backend.outils import format_moteur

        messages = _messages_depuis(getattr(requete, "messages", None))
        options = _options_depuis(getattr(requete, "parametres", None))
        outils = format_moteur()
        debut = time.monotonic()
        tokens = 0

        # UN SEUL appel au moteur par tour, outils déclarés dedans. Le tour suivant n'a lieu que si
        # le modèle a réellement demandé un outil ; sinon la boucle s'arrête au premier passage.
        for tour in range(TOURS_OUTILS_MAX):
            recu: list[str] = []
            async for morceau in superviseur.generer(messages, options, outils):
                if morceau.type == "token" and morceau.contenu:
                    tokens += 1
                    recu.append(morceau.contenu)
                    yield {"texte": morceau.contenu}
                elif morceau.type == "erreur":
                    # Le flux HTTP est déjà ouvert : signaler dedans est la seule façon d'informer.
                    logger.error("Génération interrompue par le moteur : {}", morceau.contenu)
                    raise RuntimeError(morceau.contenu or "Le moteur a interrompu la génération.")
            appels = _appels_demandes("".join(recu))
            if not appels or not outils:
                break
            messages = list(messages) + [MessageChat(role="assistant", content="".join(recu))]
            async for etape in _executer_appels(appels, messages):
                texte = etape.get("texte")
                if isinstance(texte, str):
                    yield {"texte": texte}
        else:
            logger.warning("Borne de {} tours d'outils atteinte.", TOURS_OUTILS_MAX)

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
