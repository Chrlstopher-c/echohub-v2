"""Persistance du domaine `fichiers` — table `fichiers_conversation`.

Le schéma de la table est créé par le domaine `chat` (`backend/chat/depot.py`, `_SCHEMA_CHAT_SQL`) :
c'est là que vit déjà le mécanisme additif et idempotent qui gouverne le schéma des tables propres
au chat, et `fichiers_conversation` référence `conversations(id)` par une clé étrangère. Ce module
ne fait qu'y lire et écrire, comme `backend/chat/depot.py` le fait pour ses propres tables.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.core import execute, fetch_all, fetch_one
from backend.fichiers.modeles import FichierConversation

_INSERT_FICHIER = """
INSERT INTO fichiers_conversation
    (id, conversation_id, message_id, origine, nom_affiche, chemin_relatif, type_mime, taille_octets,
     empreinte_sha256, cree_le)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_FICHIER = """
SELECT id, conversation_id, message_id, origine, nom_affiche, chemin_relatif, type_mime,
       taille_octets, empreinte_sha256, cree_le
FROM fichiers_conversation
"""


class _LigneTaille(BaseModel):
    """Ligne brute de la somme des tailles cumulées."""

    total: int


def enregistrer_fichier(fichier: FichierConversation) -> None:
    """Écrit la référence — les octets sont déjà sur le disque à cet instant, jamais l'inverse."""
    execute(
        _INSERT_FICHIER,
        (
            fichier.id,
            fichier.conversation_id,
            fichier.message_id,
            fichier.origine,
            fichier.nom_affiche,
            fichier.chemin_relatif,
            fichier.type_mime,
            fichier.taille_octets,
            fichier.empreinte_sha256,
            fichier.cree_le.isoformat(),
        ),
    )


def lire_fichier(fichier_id: str) -> FichierConversation | None:
    """Retourne la référence, ou `None` si elle n'existe pas."""
    return fetch_one(FichierConversation, f"{_SELECT_FICHIER} WHERE id = ?", (fichier_id,))


def lister_fichiers(conversation_id: str) -> list[FichierConversation]:
    """Tous les fichiers d'une conversation, dans l'ordre où ils ont été déposés."""
    return fetch_all(
        FichierConversation,
        f"{_SELECT_FICHIER} WHERE conversation_id = ? ORDER BY cree_le ASC",
        (conversation_id,),
    )


def taille_cumulee(conversation_id: str) -> int:
    """Somme des tailles déjà enregistrées pour cette conversation — 0 si aucune."""
    ligne = fetch_one(
        _LigneTaille,
        "SELECT COALESCE(SUM(taille_octets), 0) AS total FROM fichiers_conversation WHERE conversation_id = ?",
        (conversation_id,),
    )
    return ligne.total if ligne is not None else 0
