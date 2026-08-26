"""Registre des outils disponibles, et exécution d'un appel demandé par le modèle.

Le registre est la source unique de ce que le modèle peut faire : le socle de prompt système le
lit, la génération lui passe les mêmes descriptions, et l'exécution passe par lui. Un outil ajouté
ici devient visible partout ; il n'y a pas de seconde liste à tenir à jour.

Un outil ne s'enregistre que s'il est réellement utilisable. La recherche web dépend de SearXNG :
le service peut être éteint, et déclarer un outil qui échouera à chaque appel serait pire que ne
pas le déclarer — le modèle promettrait une capacité absente, exactement le défaut corrigé ici.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from backend.outils.contrat import ContexteExecution, DescriptionOutil, EchecOutil, Outil, ResultatOutil
from backend.outils.executer_commande import OUTIL as OUTIL_COMMANDE
from backend.outils.executer_python import OUTIL as OUTIL_PYTHON
from backend.outils.explorer_bac import OUTIL_CHERCHER, OUTIL_LISTER
from backend.outils.fichiers_bac import OUTIL_ECRIRE, OUTIL_LIRE, OUTIL_MODIFIER
from backend.outils.presenter_fichier import OUTIL as OUTIL_PRESENTER
from backend.outils.recherche_web import OUTIL as OUTIL_RECHERCHE
from backend.outils.recuperer_page import OUTIL as OUTIL_PAGE

# Ordre significatif : c'est celui dans lequel les outils sont présentés au modèle, et le premier
# est celui vers lequel il se tourne le plus volontiers. La recherche web est en tête parce que
# c'est l'absence de sources qui produit le plus d'inventions.
#
# Viennent ensuite les trois outils de fichier DANS L'ORDRE DE LA BOUCLE DE TRAVAIL — écrire, lire,
# modifier — puis l'exécution. Ce n'est pas cosmétique : jusqu'au 2026-08-16, `executer_python`
# était le seul moyen de produire un fichier, le modèle emballait donc son contenu dans du source
# Python et réécrivait TOUT à chaque erreur. Présenter l'écriture avant l'exécution pousse à poser
# le fichier d'abord, ce qui rend la correction suivante possible au lieu d'être une réémission.
#
# La présentation vient en dernier : elle ne fait jamais rien sans qu'un fichier existe déjà.
#
# Quatre outils ajoutés le 2026-08-26, chacun placé par la même règle — à côté de celui dont il est
# la suite naturelle, jamais en fin de liste :
#
# - `recuperer_page` suit immédiatement `recherche_web`, parce que c'est sa seconde moitié : la
#   recherche rend des adresses et des extraits de deux lignes, et un extrait ne permet pas de
#   répondre. Sans lui, le harnais réclamait des sources tout en laissant le modèle combler de
#   mémoire — l'écart exact que le socle interdit ;
# - `lister_fichiers` et `chercher_dans_fichiers` s'intercalent APRÈS les trois outils de fichier
#   et AVANT l'exécution. Le socle exige déjà « your memory of what you wrote is not the file »
#   sans donner le moyen d'y obéir ; voir avant d'agir doit précéder agir ;
# - `executer_commande` suit `executer_python` et ne le remplace pas. L'ordre compte ici comme
#   ailleurs : présenter le shell d'abord ferait glisser vers `bash -c python3 …` tout ce qui
#   relève de Python, et on perdrait le confinement mieux ajusté du second.
_OUTILS: dict[str, Outil] = {
    OUTIL_RECHERCHE.nom: OUTIL_RECHERCHE,
    OUTIL_PAGE.nom: OUTIL_PAGE,
    OUTIL_ECRIRE.nom: OUTIL_ECRIRE,
    OUTIL_LIRE.nom: OUTIL_LIRE,
    OUTIL_MODIFIER.nom: OUTIL_MODIFIER,
    OUTIL_LISTER.nom: OUTIL_LISTER,
    OUTIL_CHERCHER.nom: OUTIL_CHERCHER,
    OUTIL_PYTHON.nom: OUTIL_PYTHON,
    OUTIL_COMMANDE.nom: OUTIL_COMMANDE,
    OUTIL_PRESENTER.nom: OUTIL_PRESENTER,
}


def disponibles() -> list[Outil]:
    return list(_OUTILS.values())


def descriptions() -> list[DescriptionOutil]:
    return [outil.description for outil in _OUTILS.values()]


def format_moteur() -> list[dict[str, Any]]:
    """Liste `tools=` telle que `create_chat_completion` l'attend."""
    return [outil.description.vers_format_moteur() for outil in _OUTILS.values()]


def _arguments(brut: object) -> dict[str, Any]:
    """Les arguments arrivent en JSON sérialisé, parfois mal formé — un modèle n'est pas un parseur.

    Un JSON invalide n'est pas une erreur fatale : il devient un résultat d'échec que le modèle
    lira, et il pourra corriger son appel au tour suivant.
    """
    if isinstance(brut, dict):
        return brut
    if not isinstance(brut, str) or not brut.strip():
        return {}
    try:
        charge = json.loads(brut)
    except json.JSONDecodeError as exc:
        logger.warning("Arguments d'outil illisibles ({}) : {!r}", exc, brut[:200])
        return {}
    return charge if isinstance(charge, dict) else {}


async def executer(nom: str, arguments_bruts: object, contexte: ContexteExecution) -> ResultatOutil:
    """Exécute l'outil demandé. Ne lève jamais : un échec est un résultat rendu au modèle.

    `contexte` porte l'identité de la conversation appelante : le registre la REÇOIT en paramètre,
    il ne la devine ni ne la lit sur un état partagé (plan d'exécution, section 2.5).
    """
    arguments = _arguments(arguments_bruts)
    outil = _OUTILS.get(nom)
    if outil is None:
        connus = ", ".join(sorted(_OUTILS)) or "aucun"
        logger.warning("Outil inconnu demandé par le modèle : {}", nom)
        return ResultatOutil(
            nom=nom,
            succes=False,
            arguments=arguments,
            texte=f"L'outil « {nom} » n'existe pas. Outils disponibles : {connus}.",
        )
    # Synonymes ramenés à leur nom canonique AVANT exécution. `arguments` conserve la forme reçue
    # pour l'affichage : l'utilisateur doit voir ce que le modèle a réellement demandé, pas ce que
    # le harnais en a fait.
    normalises = outil.description.normaliser(arguments)
    if normalises != arguments:
        logger.info(
            "Arguments de {} normalisés : {} -> {}", nom, sorted(arguments), sorted(normalises)
        )
    try:
        texte = await outil.executer(normalises, contexte)
    except EchecOutil as exc:
        # Échec ATTENDU : le message est déjà rédigé pour le modèle, il part sans enrobage. Le
        # distinguer d'une panne est ce qui permet au harnais de savoir qu'un tour n'a rien produit.
        logger.info("Outil {} en échec attendu : {}", nom, exc)
        return ResultatOutil(nom=nom, succes=False, arguments=arguments, texte=str(exc)).tronque()
    except Exception as exc:  # noqa: BLE001 — un outil qui explose ne doit pas tuer la génération
        logger.exception("Outil {} a échoué", nom)
        return ResultatOutil(nom=nom, succes=False, arguments=arguments, texte=f"Échec de l'outil : {exc}").tronque()
    logger.info("Outil {} exécuté ({} caractères rendus)", nom, len(texte))
    return ResultatOutil(nom=nom, succes=True, arguments=arguments, texte=texte).tronque()
