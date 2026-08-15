"""Disque du domaine `fichiers` — un dossier par conversation, dérivé de `settings.data_home`.

Disposition imposée par le plan d'exécution (section 2.1) :

    <data_home>/echohub-v2/conversations/<conversation_id>/fichiers/<id_fichier>.<ext>   ← ici
    <data_home>/echohub-v2/conversations/<conversation_id>/bac/                          ← lot L2

Aucun chemin n'est codé en dur : tout dérive de `Settings.data_home`, exactement comme
`models_dir` et `engines_dir` (`backend/core/config.py`). Les octets ne vivent jamais en base :
c'est ce module qui les porte, la table `fichiers_conversation` ne garde qu'une référence.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from backend.core import ErreurPersistance, get_settings
from backend.core.config import NOM_APPLICATION


def racine_conversations() -> Path:
    """Racine du magasin, sous le répertoire de données applicatif — jamais un chemin absolu fixe."""
    return get_settings().data_home / NOM_APPLICATION / "conversations"


def dossier_fichiers(conversation_id: str) -> Path:
    return racine_conversations() / conversation_id / "fichiers"


def ecrire_fichier(conversation_id: str, fichier_id: str, extension: str, octets: bytes) -> str:
    """Écrit les octets sur le disque et rend le chemin relatif à `racine_conversations()`.

    Le nom sur disque est `<fichier_id><extension>` : deux identifiants générés par le serveur
    (UUID côté service, extension dérivée du type MIME validé), jamais un segment fourni par
    l'utilisateur ou le modèle.
    """
    dossier = dossier_fichiers(conversation_id)
    chemin = dossier / f"{fichier_id}{extension}"
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(octets)
    except OSError as exc:
        logger.error("Écriture du fichier {} impossible : {}", chemin, exc)
        raise ErreurPersistance(f"Écriture du fichier impossible : {chemin}", details={"cause": str(exc)}) from exc
    return str(chemin.relative_to(racine_conversations()))


def chemin_absolu(chemin_relatif: str) -> Path:
    """Résout un chemin relatif enregistré en base, borné à `racine_conversations()`.

    Le chemin vient d'une ligne de base construite uniquement par `ecrire_fichier` (identifiants
    UUID, jamais de segment fourni par un utilisateur) : la vérification ci-dessous est un second
    filet, pas la garantie elle-même — un futur appelant qui construirait ce chemin autrement ne
    doit jamais pouvoir sortir du magasin.
    """
    racine = racine_conversations().resolve()
    resolu = (racine_conversations() / chemin_relatif).resolve()
    if resolu != racine and not resolu.is_relative_to(racine):
        raise ErreurPersistance(f"Chemin de fichier hors du magasin : {chemin_relatif}")
    return resolu


def supprimer_dossier_conversation(conversation_id: str) -> None:
    """Supprime le dossier complet d'une conversation (fichiers ET bac). Idempotent : silencieux
    si le dossier n'existe déjà plus."""
    dossier = racine_conversations() / conversation_id
    try:
        if dossier.exists():
            shutil.rmtree(dossier)
            logger.debug("Dossier de conversation supprimé : {}", dossier)
    except OSError as exc:
        logger.error("Suppression du dossier {} impossible : {}", dossier, exc)
        raise ErreurPersistance(f"Suppression du dossier impossible : {dossier}", details={"cause": str(exc)}) from exc
