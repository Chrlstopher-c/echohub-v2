"""Balayage du bac après exécution — c'est lui qui unifie pièces jointes et artefacts (plan, 2.1).

Le modèle n'appelle aucune API d'enregistrement : il écrit des fichiers dans son bac, point. Ce
module compare le contenu du bac avant et après une exécution, et enregistre chaque fichier nouveau
dans le magasin de `backend.fichiers`, avec `origine='modele'` — le MÊME mécanisme qu'une pièce
jointe par l'utilisateur, distingué uniquement par cette colonne.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from loguru import logger

from backend.core import EchoHubError
from backend.fichiers import FichierConversation, deposer_fichier


def etat_bac(racine_bac: Path) -> frozenset[str]:
    """Instantané des fichiers présents (chemins relatifs au bac), pris AVANT l'exécution.

    Absence du dossier = bac vide, pas une erreur : rien n'y a encore jamais été écrit.
    """
    if not racine_bac.is_dir():
        return frozenset()
    return frozenset(str(p.relative_to(racine_bac)) for p in racine_bac.rglob("*") if p.is_file())


def balayer_et_enregistrer(
    conversation_id: str, racine_bac: Path, avant: frozenset[str]
) -> list[FichierConversation]:
    """Enregistre dans le magasin les fichiers apparus dans le bac depuis `avant`.

    Un fichier qui échoue à un quota ou à la liste blanche des types MIME (`fichiers/politique.py`)
    est journalisé et ignoré — jamais fatal aux autres fichiers produits par la même exécution, ni
    au résultat rendu au modèle : un plafond dépassé ne doit pas ressembler à une exécution ratée.
    """
    apres = etat_bac(racine_bac)
    nouveaux = sorted(apres - avant)
    enregistres: list[FichierConversation] = []
    for chemin_relatif in nouveaux:
        chemin = racine_bac / chemin_relatif
        try:
            octets = chemin.read_bytes()
        except OSError as exc:
            logger.warning("Fichier produit {} illisible après exécution : {}", chemin_relatif, exc)
            continue
        type_mime, _ = mimetypes.guess_type(chemin_relatif)
        try:
            fichier = deposer_fichier(
                conversation_id,
                nom_fourni=chemin_relatif,
                type_mime_declare=type_mime,
                octets=octets,
                origine="modele",
            )
        except EchoHubError as exc:
            logger.warning("Fichier produit {} non enregistré dans le magasin : {}", chemin_relatif, exc)
            continue
        enregistres.append(fichier)
    return enregistres
