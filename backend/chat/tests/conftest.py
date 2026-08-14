"""Fixtures des tests du domaine `chat` — une base SQLite jetable par cas, aucun état partagé.

La base réelle du poste n'est jamais touchée : `XDG_DATA_HOME` pointe sur le répertoire temporaire
du test, et le cache de configuration comme la connexion du thread sont vidés avant et après.
Sans ce double nettoyage, un cas hériterait de la connexion ouverte par le précédent, donc de son
fichier de base — le genre de couplage qui rend un échec de test inexplicable.
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
def chemin_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isole la base du cas de test et rend son chemin, sans créer le schéma."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    reset_settings_cache()
    close_connection()
    annulation.reinitialiser()
    yield get_settings().db_path
    close_connection()
    reset_settings_cache()
    annulation.reinitialiser()


@pytest.fixture
def base(chemin_base: Path) -> Path:
    """Base vierge, schéma commun et schéma du chat créés — l'état d'un backend qui vient de démarrer."""
    init_db()
    assurer_schema_chat()
    return chemin_base


@pytest.fixture
def conversation(base: Path) -> ResumeConversation:
    """Une conversation vide, prête à recevoir des messages."""
    return creer_conversation("Essai", None, ReglagesConversation())
