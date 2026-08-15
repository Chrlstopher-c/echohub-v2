"""Disque du domaine `fichiers` — chemins dérivés de `data_home`, jamais codés en dur."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core import ErreurPersistance
from backend.core.config import NOM_APPLICATION
from backend.fichiers import stockage


def test_racine_derive_de_data_home(racine_data_home: Path) -> None:
    assert stockage.racine_conversations() == racine_data_home / NOM_APPLICATION / "conversations"


def test_ecrire_fichier_cree_le_dossier_et_le_fichier(base: Path) -> None:
    chemin_relatif = stockage.ecrire_fichier("conv-1", "fichier-1", ".txt", b"contenu")
    chemin_absolu = stockage.chemin_absolu(chemin_relatif)
    assert chemin_absolu.read_bytes() == b"contenu"
    assert chemin_absolu.parent == stockage.dossier_fichiers("conv-1")


def test_chemin_absolu_refuse_une_sortie_du_magasin(base: Path) -> None:
    with pytest.raises(ErreurPersistance):
        stockage.chemin_absolu("../../../../etc/passwd")


def test_supprimer_dossier_conversation_est_idempotent(base: Path) -> None:
    """Aucune erreur si le dossier n'a jamais existé — la suppression d'une conversation sans
    fichier ne doit jamais échouer sur ce point."""
    stockage.supprimer_dossier_conversation("jamais-cree")


def test_supprimer_dossier_conversation_efface_reellement(base: Path) -> None:
    stockage.ecrire_fichier("conv-2", "fichier-1", ".txt", b"contenu")
    dossier_conversation = stockage.racine_conversations() / "conv-2"
    assert dossier_conversation.exists()

    stockage.supprimer_dossier_conversation("conv-2")

    assert not dossier_conversation.exists()
