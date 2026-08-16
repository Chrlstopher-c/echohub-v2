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
    PartieContenu,
    PartieImageChemin,
    PartieTexte,
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
    """Convertit les messages de la conversation au format des moteurs (`content`, pas `contenu`).

    Un message sans pièce jointe garde `content` en texte simple — forme inchangée depuis avant ce
    lot. Un message AVEC pièces devient une liste de parties (texte, puis images). Aucune image
    n'est encodée ici : `content` porte encore des CHEMINS disque (`PartieImageChemin`), jamais du
    base64 — c'est l'adaptateur moteur qui encode, au tout dernier moment (plan d'exécution, 2.2.4).
    """
    convertis: list[MessageChat] = []
    for message in messages or ():
        role = getattr(message, "role", None)
        contenu = getattr(message, "contenu", None)
        if contenu is None:
            contenu = getattr(message, "content", None)
        if role is None or contenu is None:
            logger.warning("Message ignoré, forme inattendue : {}", type(message).__name__)
            continue
        pieces = getattr(message, "pieces", None) or ()
        convertis.append(MessageChat(role=role, content=_contenu_moteur(contenu, pieces)))
    return convertis


def _contenu_moteur(contenu: str, pieces: object) -> str | list[PartieContenu]:
    """`content` du contrat moteur : texte simple sans pièce jointe, liste de parties sinon."""
    if not pieces:
        return contenu
    parties: list[PartieContenu] = []
    if contenu:
        parties.append(PartieTexte(text=contenu))
    for piece in pieces:
        chemin = getattr(piece, "chemin", None)
        type_mime = getattr(piece, "type_mime", None)
        if chemin is None or type_mime is None:
            logger.warning("Pièce jointe ignorée, forme inattendue : {}", type(piece).__name__)
            continue
        nom_affiche = getattr(piece, "nom_affiche", None) or ""
        parties.append(PartieImageChemin(chemin=str(chemin), type_mime=type_mime, nom_affiche=nom_affiche))
    return parties if parties else contenu


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

# Le bloc porte deux parties distinctes : ce que le modèle a DEMANDÉ, puis ce que l'outil a RENDU.
# Les séparer n'est pas cosmétique — juger une réponse suppose de voir la requête qui l'a produite,
# et une recherche mal formulée explique souvent un résultat hors sujet. L'entrée part avant
# l'exécution, la sortie après : l'utilisateur voit donc la demande pendant que l'outil travaille.
BALISE_ENTREE_OUVRANTE = "<entree>"
BALISE_ENTREE_FERMANTE = "</entree>"
BALISE_SORTIE_OUVRANTE = "<sortie>"
BALISE_SORTIE_FERMANTE = "</sortie>"

# Marqueur de fin d'étape, posé quand le tour qui vient de s'achever a demandé un outil.
#
# Un modèle commente son travail avant d'appeler : « je vais chercher », « j'ai obtenu 6 résultats,
# je synthétise ». Ce commentaire n'est pas la réponse, et le laisser dans le flux le fait passer
# pour telle — parfois affiché en clair, parfois avalé dans un bloc de raisonnement selon que le
# modèle a balisé ou non. Le même contenu changeait donc de traitement d'un tour à l'autre.
#
# Le marqueur est posé APRÈS coup plutôt qu'une balise ouverte à l'avance : au début d'un tour, rien
# ne dit encore s'il produira un appel d'outil ou la réponse finale. Ouvrir une balise « au cas où »
# replierait la réponse quand aucun outil n'est demandé — c'est-à-dire la plupart du temps.
# Le streaming reste donc intact : l'utilisateur voit le texte arriver, et il est reclassé une fois
# l'appel connu.
BALISE_FIN_ETAPE = "<etape-fin/>"


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
    contexte: ContexteExecution,
) -> AsyncIterator[dict[str, Any]]:
    """Exécute les appels demandés, en annonçant chacun dans le flux, et enrichit la conversation."""
    from backend.outils import executer

    for appel in appels:
        nom, arguments = _texte_appel(appel)
        # L'entrée part AVANT l'exécution : c'est ce qui rend l'attente lisible plutôt que muette.
        entree = f"{BALISE_ENTREE_OUVRANTE}{_annonce(nom, arguments)}{BALISE_ENTREE_FERMANTE}"
        yield {"texte": f"{BALISE_OUTIL_OUVRANTE}{entree}{BALISE_SORTIE_OUVRANTE}"}
        resultat = await executer(nom, arguments, contexte)
        etat = "résultat" if resultat.succes else "échec"
        yield {"texte": f"{resultat.texte}{BALISE_SORTIE_FERMANTE}{BALISE_OUTIL_FERMANTE}\n\n"}
        messages.append(MessageChat(role="assistant", content=f"[outil {resultat.nom} — {etat}]\n{resultat.texte}"))


async def _resoudre_outils(
    messages: list[MessageChat],
    options: OptionsGeneration,
    contexte: ContexteExecution,
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
            resultat = await executer(nom, arguments, contexte)
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
        from backend.fichiers.stockage import racine_conversations
        from backend.outils import format_moteur
        from backend.outils.contrat import ContexteExecution

        messages = _messages_depuis(getattr(requete, "messages", None))
        options = _options_depuis(getattr(requete, "parametres", None))
        outils = format_moteur()

        # L'identité de la conversation doit atteindre l'exécution d'un outil (plan d'exécution,
        # section 2.5) : sans elle, un outil confiné écrirait dans le bac de n'importe qui. Elle est
        # obligatoire sur `RequeteGeneration` ; son absence ici signalerait un appelant qui viole le
        # contrat du port, pas un cas normal à dégrader silencieusement.
        conversation_id = getattr(requete, "conversation_id", None)
        if not conversation_id:
            raise ValueError("RequeteGeneration sans conversation_id : contrat du port violé.")
        contexte = ContexteExecution(
            conversation_id=conversation_id,
            racine_bac=racine_conversations() / conversation_id / "bac",
        )
        debut = time.monotonic()
        tokens = 0

        # UN SEUL appel au moteur par tour, outils déclarés dedans. Le tour suivant n'a lieu que si
        # le modèle a réellement demandé un outil ; sinon la boucle s'arrête au premier passage.
        #
        # DEUX notions distinctes, et les confondre a coûté cher :
        #
        # - `outils_declares` : ce qu'on montre au moteur. Transmis AU PREMIER TOUR SEULEMENT. Dès
        #   qu'un tour a produit des résultats, il repasse à `None` — sinon le modèle voit encore
        #   les mêmes outils après les avoir déjà reçus et n'a aucune raison d'arrêter d'en
        #   redemander (plan d'exécution, L10-b).
        # - `outils` : le fait qu'un registre existe. Il ne bouge pas de la boucle, et c'est lui
        #   qui autorise l'EXÉCUTION.
        #
        # La sortie de boucle ne doit dépendre que des appels réellement demandés. Mesuré le
        # 2026-08-16 en conditions réelles : le modèle demandait `presenter_fichier` au second
        # tour, l'appel était bien détecté, mais la condition portait aussi sur les outils déclarés
        # — devenus `None` — donc la boucle sortait SANS exécuter, et le `<tool_call>` restait
        # affiché en XML brut dans la réponse. Ne plus déclarer un outil n'est pas la même chose
        # que refuser de faire ce que le modèle demande ; c'est `TOURS_OUTILS_MAX` qui borne, pas
        # cette condition.
        outils_declares = outils or None
        for tour in range(TOURS_OUTILS_MAX):
            recu: list[str] = []
            async for morceau in superviseur.generer(messages, options, outils_declares):
                if morceau.type == "token" and morceau.contenu:
                    tokens += 1
                    recu.append(morceau.contenu)
                    yield {"texte": morceau.contenu}
                elif morceau.type == "erreur":
                    # Le flux HTTP est déjà ouvert : signaler dedans est la seule façon d'informer.
                    logger.error("Génération interrompue par le moteur : {}", morceau.contenu)
                    raise RuntimeError(morceau.contenu or "Le moteur a interrompu la génération.")
            # Sans registre, un `<tool_call>` écrit par le modèle est une hallucination : l'exécuter
            # produirait un bloc « outil inconnu » là où il n'y a simplement aucun outil.
            appels = _appels_demandes("".join(recu)) if outils else []
            if not appels:
                break
            # Ce tour appelait un outil : ce qui vient d'être écrit était donc du commentaire de
            # travail, pas la réponse. On le signale au lieu de le laisser passer pour une réponse.
            yield {"texte": BALISE_FIN_ETAPE}
            messages = list(messages) + [MessageChat(role="assistant", content="".join(recu))]
            async for etape in _executer_appels(appels, messages, contexte):
                texte = etape.get("texte")
                if isinstance(texte, str):
                    yield {"texte": texte}
            # Résultats rendus : le tour suivant ne reverra plus les outils déclarés.
            outils_declares = None
        else:
            # Borne atteinte : les trois tours ont TOUS demandé un outil, donc aucun n'a produit de
            # réponse. Sortir ici laissait la conversation sans un mot — l'interface affichait
            # « le modèle n'a rien écrit en dehors de son raisonnement » sous une pile de blocs
            # d'outils. Mesuré le 2026-08-16 sur un modèle qui réémettait un appel vide en boucle.
            #
            # Un tour de plus, sans outil déclaré et sans droit d'en appeler, garantit qu'il reste
            # une réponse. Ce n'est pas une quatrième chance donnée à l'outil : c'est la clôture.
            logger.warning(
                "Borne de {} tours d'outils atteinte : tour de clôture sans outil.", TOURS_OUTILS_MAX
            )
            yield {"texte": BALISE_FIN_ETAPE}
            async for morceau in superviseur.generer(messages, options, None):
                if morceau.type == "token" and morceau.contenu:
                    tokens += 1
                    yield {"texte": morceau.contenu}
                elif morceau.type == "erreur":
                    logger.error("Tour de clôture interrompu par le moteur : {}", morceau.contenu)
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
