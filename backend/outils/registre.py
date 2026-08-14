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

from backend.outils.contrat import DescriptionOutil, Outil, ResultatOutil
from backend.outils.recherche_web import OUTIL as OUTIL_RECHERCHE

# Ordre significatif : c'est celui dans lequel les outils sont présentés au modèle, et le premier
# est celui vers lequel il se tourne le plus volontiers. La recherche web est en tête parce que
# c'est l'absence de sources qui produit le plus d'inventions.
_OUTILS: dict[str, Outil] = {OUTIL_RECHERCHE.nom: OUTIL_RECHERCHE}


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


async def executer(nom: str, arguments_bruts: object) -> ResultatOutil:
    """Exécute l'outil demandé. Ne lève jamais : un échec est un résultat rendu au modèle."""
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
    try:
        texte = await outil.executer(arguments)
    except Exception as exc:  # noqa: BLE001 — un outil qui explose ne doit pas tuer la génération
        logger.exception("Outil {} a échoué", nom)
        return ResultatOutil(nom=nom, succes=False, arguments=arguments, texte=f"Échec de l'outil : {exc}").tronque()
    logger.info("Outil {} exécuté ({} caractères rendus)", nom, len(texte))
    return ResultatOutil(nom=nom, succes=True, arguments=arguments, texte=texte).tronque()
