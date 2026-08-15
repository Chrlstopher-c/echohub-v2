"""Persistance du domaine `fichiers` — table `fichiers_conversation`.

Le schéma de la table est créé par le domaine `chat` (`backend/chat/depot.py`, `_SCHEMA_CHAT_SQL`) :
c'est là que vit déjà le mécanisme additif et idempotent qui gouverne le schéma des tables propres
au chat, et `fichiers_conversation` référence `conversations(id)` par une clé étrangère. Ce module
ne fait qu'y lire et écrire, comme `backend/chat/depot.py` le fait pour ses propres tables.
"""

from __future__ import annotations

from collections.abc import Sequence

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


def lier_message(fichier_id: str, message_id: str) -> None:
    """Rattache un fichier déjà déposé au message qui vient de l'envoyer.

    Le fichier est uploadé AVANT que le message n'existe (le composeur dépose la pièce dès qu'elle
    est choisie) : cette écriture referme le lien une fois le message persisté.
    """
    execute("UPDATE fichiers_conversation SET message_id = ? WHERE id = ?", (message_id, fichier_id))


def lister_par_messages(message_ids: Sequence[str]) -> dict[str, list[FichierConversation]]:
    """Fichiers liés à ces messages, groupés par `message_id` — une seule requête, pas une par message.

    Un dictionnaire absent d'une clé signifie « aucune pièce jointe », l'appelant ne doit pas le
    distinguer d'une liste vide.
    """
    if not message_ids:
        return {}
    marqueurs = ", ".join("?" for _ in message_ids)
    lignes = fetch_all(
        FichierConversation,
        f"{_SELECT_FICHIER} WHERE message_id IN ({marqueurs}) ORDER BY cree_le ASC",
        tuple(message_ids),
    )
    groupes: dict[str, list[FichierConversation]] = {}
    for fichier in lignes:
        # `message_id` est garanti non nul ici : la clause `IN` ne peut matcher que des lignes liées.
        # Gardé en `if` plutôt qu'en `assert` : jamais désactivé, quel que soit le mode d'exécution.
        if fichier.message_id is None:
            continue
        groupes.setdefault(fichier.message_id, []).append(fichier)
    return groupes
