"""Fixtures des tests du domaine `outils` — base et disque isolés par cas, comme `backend.fichiers.tests`.

Le bac à sable écrit dans le magasin `fichiers` : ces tests ont donc besoin du même schéma
(`fichiers_conversation`, porté par `backend.chat.depot`) et d'une conversation réelle à qui
rattacher les fichiers produits.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.chat import annulation
from backend.chat.depot import assurer_schema_chat, creer_conversation
from backend.chat.modeles import ReglagesConversation, ResumeConversation
from backend.core import close_connection, init_db
from backend.core.config import reset_settings_cache
# Import direct du sous-module, pas de `backend.fichiers` : même précédent que
# `backend/inference/__init__.py::MoteurChat._flux`, qui construit `racine_bac` de la même façon.
from backend.fichiers.stockage import racine_conversations


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
def conversation(base: Path) -> ResumeConversation:
    """Une conversation vide, prête à faire tourner du code dans son bac."""
    return creer_conversation("Essai bac à sable", None, ReglagesConversation())


@pytest.fixture
def racine_bac(conversation: ResumeConversation) -> Path:
    """Bac de cette conversation, dérivé exactement comme `MoteurChat._flux` le construit."""
    return racine_conversations() / conversation.id / "bac"
