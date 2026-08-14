"""Migrations sur une base EXISTANTE — le cas qui compte : celle de l'utilisateur, avec ses données.

Chaque cas part d'un fichier écrit au schéma v1 (sans `parent_id`, avec `max_tokens: 1024` figé),
puis vérifie qu'après démarrage : rien n'est perdu, l'historique se relit dans le même ordre, et
les migrations ne rejouent pas.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.chat import depot
from backend.core import close_connection, init_db

_SCHEMA_V1 = """
CREATE TABLE conversations (
    id TEXT PRIMARY KEY, titre TEXT NOT NULL, modele_id TEXT,
    cree_le TEXT NOT NULL, maj_le TEXT NOT NULL, archivee INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
    contenu TEXT NOT NULL, tokens_generes INTEGER, tokens_par_seconde REAL, cree_le TEXT NOT NULL
);
CREATE TABLE chat_reglages (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    prompt_systeme TEXT NOT NULL DEFAULT '', parametres TEXT NOT NULL,
    historique_max_messages INTEGER, maj_le TEXT NOT NULL
);
PRAGMA user_version=1;
"""

_PARAMETRES_V1 = {
    "temperature": 0.8,
    "top_p": 0.95,
    "top_k": 40,
    "penalite_repetition": 1.1,
    "max_tokens": 1024,
    "sequences_arret": [],
    "graine": None,
}


def ecrire_base_v1(chemin: Path, *, max_tokens: int = 1024) -> None:
    """Reproduit une base d'utilisateur : une conversation, quatre messages, réglages figés."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(chemin))
    try:
        conn.executescript(_SCHEMA_V1)
        conn.execute(
            "INSERT INTO conversations (id, titre, cree_le, maj_le) VALUES ('c1', 'Reprise', ?, ?)",
            ("2026-08-01T10:00:00+00:00", "2026-08-01T10:03:00+00:00"),
        )
        for rang, (identifiant, role, contenu) in enumerate(
            [
                ("m1", "user", "bonjour"),
                ("m2", "assistant", "salut"),
                ("m3", "user", "et ensuite ?"),
                ("m4", "assistant", "voilà"),
            ]
        ):
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, contenu, cree_le) VALUES (?, 'c1', ?, ?, ?)",
                (identifiant, role, contenu, f"2026-08-01T10:0{rang}:00+00:00"),
            )
        conn.execute(
            "INSERT INTO chat_reglages (conversation_id, prompt_systeme, parametres, maj_le) VALUES"
            " ('c1', '', ?, ?)",
            (json.dumps({**_PARAMETRES_V1, "max_tokens": max_tokens}), "2026-08-01T10:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def demarrer() -> None:
    """Ce que fait `main._preparer_persistance()` au démarrage du backend."""
    init_db()
    depot.assurer_schema_chat()


def test_historique_existant_est_chaine_et_relu_dans_l_ordre(chemin_base: Path) -> None:
    ecrire_base_v1(chemin_base)
    demarrer()

    messages = depot.lister_messages("c1")
    assert [m.id for m in messages] == ["m1", "m2", "m3", "m4"]
    assert [m.parent_id for m in messages] == [None, "m1", "m2", "m3"]


def test_second_demarrage_ne_rattache_pas_une_racine_legitime(chemin_base: Path) -> None:
    """Une édition du premier message crée une seconde racine : elle doit le rester."""
    ecrire_base_v1(chemin_base)
    demarrer()
    corrige = depot.ajouter_message("c1", role="user", contenu="bonjour !", parent_id=None)

    close_connection()
    demarrer()

    relu = depot.lire_message("c1", corrige.id)
    assert relu is not None
    assert relu.parent_id is None


def test_max_tokens_par_defaut_est_efface_une_seule_fois(chemin_base: Path) -> None:
    ecrire_base_v1(chemin_base)
    demarrer()
    assert depot.lire_reglages("c1").parametres.max_tokens is None

    repose = depot.lire_reglages("c1").model_copy(deep=True)
    repose.parametres.max_tokens = 1024
    depot.ecrire_reglages("c1", repose)
    close_connection()
    demarrer()
    assert depot.lire_reglages("c1").parametres.max_tokens == 1024


def test_max_tokens_choisi_par_l_utilisateur_est_preserve(chemin_base: Path) -> None:
    ecrire_base_v1(chemin_base, max_tokens=4096)
    demarrer()
    assert depot.lire_reglages("c1").parametres.max_tokens == 4096
