"""Accès SQLite — connexion WAL, schéma du MVP, lecture typée.

`core/db` fournit l'infrastructure de persistance, pas la logique métier : les domaines `chat` et
`models` construisent leurs opérations sur `transaction`, `execute`, `fetch_one` et `fetch_all`, et
typent leurs lectures avec les modèles de ligne définis ici. Le schéma reste centralisé parce qu'il
n'y a qu'un seul fichier de base à initialiser.

WAL est retenu pour que les lectures de l'interface ne bloquent pas l'écriture d'un message en
cours de streaming.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Literal, TypeVar

from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from backend.core.config import get_settings
from backend.core.errors import ErreurPersistance

T = TypeVar("T", bound=BaseModel)

SCHEMA_VERSION = 1

# Une connexion SQLite n'est pas partageable entre threads : uvicorn en utilise plusieurs, chacun
# garde donc la sienne. État partagé assumé et confiné à ce module.
_local = threading.local()

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    titre       TEXT NOT NULL DEFAULT 'Nouvelle conversation',
    modele_id   TEXT,
    cree_le     TEXT NOT NULL,
    maj_le      TEXT NOT NULL,
    archivee    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id                 TEXT PRIMARY KEY,
    conversation_id    TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role               TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
    contenu            TEXT NOT NULL,
    tokens_generes     INTEGER,
    tokens_par_seconde REAL,
    cree_le            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, cree_le);

-- Registre local : ce qui est réellement présent sur le disque. Les colonnes de métadonnées sont
-- nullables tant que l'en-tête GGUF n'a pas été lu — un NULL signifie « pas encore mesuré » et
-- n'autorise jamais une estimation à la place (défaut central de la v1 : 80 couches devinées, 41
-- réelles).
CREATE TABLE IF NOT EXISTS modeles (
    id              TEXT PRIMARY KEY,
    depot           TEXT NOT NULL,
    fichier         TEXT,
    chemin          TEXT NOT NULL,
    format          TEXT NOT NULL CHECK (format IN ('gguf', 'safetensors')),
    taille_octets   INTEGER NOT NULL,
    quantification  TEXT,
    architecture    TEXT,
    nb_couches      INTEGER,
    contexte_max    INTEGER,
    ajoute_le       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_modeles_depot ON modeles(depot);
"""


class Conversation(BaseModel):
    """Ligne de `conversations`."""

    id: str
    titre: str
    modele_id: str | None = None
    cree_le: datetime
    maj_le: datetime
    archivee: bool = False


class Message(BaseModel):
    """Ligne de `messages`. Les statistiques sont celles mesurées à la génération, pas des cibles."""

    id: str
    conversation_id: str
    role: Literal["system", "user", "assistant"]
    contenu: str
    tokens_generes: int | None = None
    tokens_par_seconde: float | None = None
    cree_le: datetime


class ModeleEnregistre(BaseModel):
    """Ligne de `modeles` — le registre local, reflet du disque."""

    id: str
    depot: str
    fichier: str | None = None
    chemin: str
    format: Literal["gguf", "safetensors"]
    taille_octets: int = Field(ge=0)
    quantification: str | None = None
    architecture: str | None = None
    nb_couches: int | None = None
    contexte_max: int | None = None
    ajoute_le: datetime


def maintenant() -> str:
    """Horodatage ISO 8601 UTC — format unique de toutes les colonnes de date."""
    return datetime.now(timezone.utc).isoformat()


def _appliquer_pragmas(conn: sqlite3.Connection) -> None:
    """WAL pour lecteurs concurrents, clés étrangères actives, attente bornée sur verrou."""
    timeout_ms = int(get_settings().db_timeout_s * 1000)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={timeout_ms}")


def get_connection() -> sqlite3.Connection:
    """Connexion du thread courant, créée à la demande."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None:
        return conn

    parametres = get_settings()
    parametres.preparer_repertoires()
    try:
        conn = sqlite3.connect(
            str(parametres.db_path),
            check_same_thread=False,
            timeout=parametres.db_timeout_s,
        )
        conn.row_factory = sqlite3.Row
        _appliquer_pragmas(conn)
    except sqlite3.Error as exc:
        logger.error("Ouverture de la base {} impossible : {}", parametres.db_path, exc)
        raise ErreurPersistance(
            f"Base de données inaccessible : {parametres.db_path}",
            details={"cause": str(exc)},
        ) from exc

    _local.conn = conn
    return conn


def close_connection() -> None:
    """Ferme la connexion du thread courant. Appelé à l'arrêt du backend et entre deux tests."""
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is None:
        return
    try:
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("Fermeture de la connexion SQLite échouée : {}", exc)
    finally:
        _local.conn = None


def init_db() -> None:
    """Crée le schéma s'il manque et vérifie la version. À appeler une fois au démarrage."""
    conn = get_connection()
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise ErreurPersistance(
            f"Base écrite par une version plus récente (schéma v{version} > v{SCHEMA_VERSION}).",
            remediation="Mettre à jour EchoHub, ou repartir d'un fichier de base vierge.",
        )

    try:
        with conn:
            conn.executescript(_SCHEMA_SQL)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    except sqlite3.Error as exc:
        logger.error("Initialisation du schéma échouée : {}", exc)
        raise ErreurPersistance("Initialisation du schéma impossible.", details={"cause": str(exc)}) from exc

    logger.info("Base prête : {} (schéma v{})", get_settings().db_path, SCHEMA_VERSION)


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Transaction : commit à la sortie normale, rollback sur exception."""
    conn = get_connection()
    try:
        with conn:
            yield conn
    except sqlite3.Error as exc:
        logger.error("Transaction annulée : {}", exc)
        raise ErreurPersistance("Écriture en base échouée.", details={"cause": str(exc)}) from exc


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Exécute une écriture et retourne le nombre de lignes affectées."""
    with transaction() as conn:
        return conn.execute(sql, tuple(params)).rowcount


def executemany(sql: str, lignes: Sequence[Sequence[Any]]) -> int:
    """Exécute une écriture répétée dans une seule transaction."""
    with transaction() as conn:
        return conn.executemany(sql, [tuple(ligne) for ligne in lignes]).rowcount


def _convertir(modele: type[T], ligne: sqlite3.Row) -> T:
    try:
        return modele.model_validate(dict(ligne))
    except ValidationError as exc:
        logger.error("Ligne incompatible avec {} : {}", modele.__name__, exc)
        raise ErreurPersistance(
            f"Donnée en base incompatible avec le modèle {modele.__name__}.",
            remediation="Le schéma et le code ont divergé : vérifier la version de la base.",
            details={"cause": str(exc)},
        ) from exc


def _lire(sql: str, params: Sequence[Any]) -> list[sqlite3.Row]:
    try:
        return get_connection().execute(sql, tuple(params)).fetchall()
    except sqlite3.Error as exc:
        logger.error("Lecture SQL échouée ({}) : {}", sql.strip().splitlines()[0], exc)
        raise ErreurPersistance("Lecture en base échouée.", details={"cause": str(exc)}) from exc


def fetch_all(modele: type[T], sql: str, params: Sequence[Any] = ()) -> list[T]:
    """Lit et type toutes les lignes retournées par la requête."""
    return [_convertir(modele, ligne) for ligne in _lire(sql, params)]


def fetch_one(modele: type[T], sql: str, params: Sequence[Any] = ()) -> T | None:
    """Lit et type la première ligne, ou `None` si la requête ne retourne rien."""
    lignes = _lire(sql, params)
    return _convertir(modele, lignes[0]) if lignes else None
