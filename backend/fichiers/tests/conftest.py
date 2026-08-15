"""Fixtures des tests du domaine `fichiers` — base et disque isolés par cas, comme `backend.chat.tests`.

La table `fichiers_conversation` vit dans le schéma du domaine `chat` (voir `backend/chat/depot.py`) :
`assurer_schema_chat()` est donc nécessaire ici aussi, exactement comme pour les tests du chat.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.chat import annulation
from backend.chat.depot import assurer_schema_chat, creer_conversation
from backend.chat.modeles import ReglagesConversation, ResumeConversation
from backend.core import close_connection, init_db
from backend.core.config import get_settings, reset_settings_cache


@pytest.fixture
def chemin_donnees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isole la base et le disque du cas de test, sans créer le schéma."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    reset_settings_cache()
    close_connection()
    annulation.reinitialiser()
    yield tmp_path
    close_connection()
    reset_settings_cache()
    annulation.reinitialiser()


@pytest.fixture
def base(chemin_donnees: Path) -> Path:
    """Base vierge, schéma commun ET schéma du chat créés (donc `fichiers_conversation` aussi)."""
    init_db()
    assurer_schema_chat()
    return chemin_donnees


@pytest.fixture
def racine_data_home(base: Path) -> Path:
    return get_settings().data_home


@pytest.fixture
def conversation(base: Path) -> ResumeConversation:
    """Une conversation vide, prête à recevoir des fichiers."""
    return creer_conversation("Essai fichiers", None, ReglagesConversation())
