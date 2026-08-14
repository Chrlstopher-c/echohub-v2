"""Persistance du domaine `chat`, bâtie sur `core.db`.

Deux tables appartiennent au domaine et sont créées ici, de façon additive et idempotente :

- `chat_reglages` — prompt système et paramètres d'échantillonnage par conversation ;
- `chat_meta_messages` — modèle ayant produit un message, et indicateur d'interruption.

Elles n'existent pas dans le schéma de `core` et ne touchent aucune de ses tables : ce sont des
besoins propres au chat, colocalisés avec le code qui les fait vivre. Si le socle finit par les
absorber, `assurer_schema_chat()` reste sans effet (CREATE TABLE IF NOT EXISTS).

Le prompt système n'est délibérément PAS stocké comme un message de rôle `system` : c'est un
réglage qu'on modifie, pas un tour de conversation qu'on relit. Le confondre avec l'historique
obligerait à réécrire un message à chaque changement de réglage.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from loguru import logger
from pydantic import BaseModel

from backend.chat.modeles import (
    MajConversation,
    MessageChat,
    ParametresEchantillonnage,
    ReglagesConversation,
    ResumeConversation,
    RoleMessage,
)
from backend.core import (
    ConversationIntrouvable,
    ErreurPersistance,
    execute,
    fetch_all,
    fetch_one,
    maintenant,
    transaction,
)

_SCHEMA_CHAT_SQL = """
CREATE TABLE IF NOT EXISTS chat_reglages (
    conversation_id         TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    prompt_systeme          TEXT NOT NULL DEFAULT '',
    parametres              TEXT NOT NULL,
    historique_max_messages INTEGER,
    maj_le                  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_meta_messages (
    message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    modele_id  TEXT,
    interrompu INTEGER NOT NULL DEFAULT 0
);
"""

# `rowid` départage deux messages écrits dans la même microseconde : l'horodatage seul ne garantit
# pas un ordre stable, et un historique dans le désordre corrompt le contexte envoyé au moteur.
_SELECT_MESSAGES = """
SELECT m.id, m.conversation_id, m.role, m.contenu, m.tokens_generes, m.tokens_par_seconde,
       m.cree_le, meta.modele_id AS modele_id, COALESCE(meta.interrompu, 0) AS interrompu
FROM messages m
LEFT JOIN chat_meta_messages meta ON meta.message_id = m.id
WHERE m.conversation_id = ?
ORDER BY m.cree_le ASC, m.rowid ASC
"""

_SELECT_CONVERSATIONS = """
SELECT c.id, c.titre, c.modele_id, c.cree_le, c.maj_le, c.archivee,
       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS nb_messages
FROM conversations c
"""

_COLONNES_MODIFIABLES: dict[str, str] = {"titre": "titre", "modele_id": "modele_id", "archivee": "archivee"}


class _LigneReglages(BaseModel):
    """Ligne brute de `chat_reglages` : les paramètres y sont un document JSON."""

    prompt_systeme: str
    parametres: str
    historique_max_messages: int | None = None


def assurer_schema_chat() -> None:
    """Crée les tables du domaine si elles manquent. Appelé une fois, après `core.init_db()`."""
    try:
        with transaction() as conn:
            conn.executescript(_SCHEMA_CHAT_SQL)
    except sqlite3.Error as exc:
        logger.error("Création du schéma chat impossible : {}", exc)
        raise ErreurPersistance("Schéma du domaine chat non initialisable.", details={"cause": str(exc)}) from exc
    logger.info("Schéma du domaine chat prêt.")


def creer_conversation(titre: str, modele_id: str | None, reglages: ReglagesConversation) -> ResumeConversation:
    """Insère la conversation et ses réglages dans une seule transaction."""
    identifiant = str(uuid.uuid4())
    horodatage = maintenant()
    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO conversations (id, titre, modele_id, cree_le, maj_le, archivee) VALUES (?, ?, ?, ?, ?, 0)",
                (identifiant, titre, modele_id, horodatage, horodatage),
            )
            conn.execute(
                "INSERT INTO chat_reglages (conversation_id, prompt_systeme, parametres,"
                " historique_max_messages, maj_le) VALUES (?, ?, ?, ?, ?)",
                (
                    identifiant,
                    reglages.prompt_systeme,
                    reglages.parametres.model_dump_json(),
                    reglages.historique_max_messages,
                    horodatage,
                ),
            )
    except sqlite3.Error as exc:
        logger.error("Création de conversation échouée : {}", exc)
        raise ErreurPersistance("Création de la conversation impossible.", details={"cause": str(exc)}) from exc

    logger.debug("Conversation créée : {} ({})", identifiant, titre)
    return ResumeConversation(id=identifiant, titre=titre, modele_id=modele_id, cree_le=horodatage, maj_le=horodatage)


def lire_conversation(conversation_id: str) -> ResumeConversation | None:
    """Retourne la conversation, ou `None` si elle n'existe pas."""
    return fetch_one(ResumeConversation, f"{_SELECT_CONVERSATIONS} WHERE c.id = ?", (conversation_id,))


def exiger_conversation(conversation_id: str) -> ResumeConversation:
    """Comme `lire_conversation`, mais lève plutôt que de rendre `None`."""
    conversation = lire_conversation(conversation_id)
    if conversation is None:
        raise ConversationIntrouvable(f"Conversation inconnue : {conversation_id}")
    return conversation


def lister_conversations(*, archivees: bool = False) -> list[ResumeConversation]:
    """Liste les conversations actives ou archivées, la plus récemment modifiée en tête."""
    return fetch_all(
        ResumeConversation,
        f"{_SELECT_CONVERSATIONS} WHERE c.archivee = ? ORDER BY c.maj_le DESC",
        (1 if archivees else 0,),
    )


def maj_conversation(conversation_id: str, patch: MajConversation) -> ResumeConversation:
    """Applique un patch partiel. Les noms de colonnes viennent d'une liste blanche, jamais du corps."""
    exiger_conversation(conversation_id)
    modifications = patch.model_dump(exclude_unset=True, exclude_none=True)
    affectations = [f"{_COLONNES_MODIFIABLES[champ]} = ?" for champ in modifications if champ in _COLONNES_MODIFIABLES]
    if not affectations:
        return exiger_conversation(conversation_id)

    valeurs = [_valeur_sql(modifications[champ]) for champ in modifications if champ in _COLONNES_MODIFIABLES]
    affectations.append("maj_le = ?")
    valeurs.extend([maintenant(), conversation_id])
    execute(f"UPDATE conversations SET {', '.join(affectations)} WHERE id = ?", valeurs)
    return exiger_conversation(conversation_id)


def _valeur_sql(valeur: object) -> object:
    """SQLite n'a pas de booléen : les stocker en 0/1 explicitement, sans dépendre de l'adaptateur."""
    return int(valeur) if isinstance(valeur, bool) else valeur


def definir_modele_conversation(conversation_id: str, modele_id: str) -> None:
    """Mémorise le modèle réellement utilisé pour le dernier tour de cette conversation."""
    execute(
        "UPDATE conversations SET modele_id = ?, maj_le = ? WHERE id = ?",
        (modele_id, maintenant(), conversation_id),
    )


def supprimer_conversation(conversation_id: str) -> None:
    """Supprime la conversation. Messages et réglages suivent par cascade (`PRAGMA foreign_keys=ON`)."""
    exiger_conversation(conversation_id)
    execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    logger.debug("Conversation supprimée : {}", conversation_id)


def lire_reglages(conversation_id: str) -> ReglagesConversation:
    """Réglages de la conversation, ou les valeurs par défaut si aucune ligne n'a été écrite."""
    ligne = fetch_one(
        _LigneReglages,
        "SELECT prompt_systeme, parametres, historique_max_messages FROM chat_reglages WHERE conversation_id = ?",
        (conversation_id,),
    )
    if ligne is None:
        return ReglagesConversation()
    return ReglagesConversation(
        prompt_systeme=ligne.prompt_systeme,
        parametres=_decoder_parametres(conversation_id, ligne.parametres),
        historique_max_messages=ligne.historique_max_messages,
    )


def _decoder_parametres(conversation_id: str, document: str) -> ParametresEchantillonnage:
    try:
        return ParametresEchantillonnage.model_validate(json.loads(document))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Paramètres illisibles pour la conversation {} : {}", conversation_id, exc)
        raise ErreurPersistance(
            "Paramètres d'échantillonnage illisibles en base.",
            remediation="Réenregistrer les réglages de cette conversation depuis l'interface.",
            details={"conversation_id": conversation_id, "cause": str(exc)},
        ) from exc


def ecrire_reglages(conversation_id: str, reglages: ReglagesConversation) -> ReglagesConversation:
    """Écrit les réglages complets de la conversation (insertion ou remplacement)."""
    exiger_conversation(conversation_id)
    execute(
        "INSERT INTO chat_reglages (conversation_id, prompt_systeme, parametres, historique_max_messages, maj_le)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(conversation_id) DO UPDATE SET prompt_systeme = excluded.prompt_systeme,"
        " parametres = excluded.parametres, historique_max_messages = excluded.historique_max_messages,"
        " maj_le = excluded.maj_le",
        (
            conversation_id,
            reglages.prompt_systeme,
            reglages.parametres.model_dump_json(),
            reglages.historique_max_messages,
            maintenant(),
        ),
    )
    return reglages


def lister_messages(conversation_id: str) -> list[MessageChat]:
    """Historique complet de la conversation, dans l'ordre d'écriture."""
    return fetch_all(MessageChat, _SELECT_MESSAGES, (conversation_id,))


def ajouter_message(
    conversation_id: str,
    role: RoleMessage,
    contenu: str,
    *,
    identifiant: str | None = None,
    modele_id: str | None = None,
    tokens_generes: int | None = None,
    tokens_par_seconde: float | None = None,
    interrompu: bool = False,
) -> MessageChat:
    """Insère un message et remonte l'horodatage de la conversation, en une transaction.

    `identifiant` permet d'imposer l'id annoncé au client à l'ouverture d'un flux : le message
    persisté doit porter le même identifiant que celui déjà affiché, sinon le frontend garde un
    message fantôme à côté du vrai.
    """
    message = MessageChat(
        id=identifiant or str(uuid.uuid4()),
        conversation_id=conversation_id,
        role=role,
        contenu=contenu,
        tokens_generes=tokens_generes,
        tokens_par_seconde=tokens_par_seconde,
        cree_le=maintenant(),
        modele_id=modele_id,
        interrompu=interrompu,
    )
    _ecrire_message(message)
    return message


def _ecrire_message(message: MessageChat) -> None:
    """Écrit le message, ses métadonnées de domaine et l'horodatage de la conversation, en un bloc.

    Les trois écritures forment une seule transaction : un message sans son horodatage remonté
    ferait remonter la conversation en fin de liste alors qu'elle vient de bouger.
    """
    horodatage = message.cree_le.isoformat()
    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, contenu, tokens_generes, tokens_par_seconde,"
                " cree_le) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    message.id,
                    message.conversation_id,
                    message.role,
                    message.contenu,
                    message.tokens_generes,
                    message.tokens_par_seconde,
                    horodatage,
                ),
            )
            if message.modele_id is not None or message.interrompu:
                conn.execute(
                    "INSERT INTO chat_meta_messages (message_id, modele_id, interrompu) VALUES (?, ?, ?)",
                    (message.id, message.modele_id, int(message.interrompu)),
                )
            conn.execute(
                "UPDATE conversations SET maj_le = ? WHERE id = ?",
                (horodatage, message.conversation_id),
            )
    except sqlite3.Error as exc:
        logger.error("Écriture du message dans {} échouée : {}", message.conversation_id, exc)
        raise ErreurPersistance("Écriture du message impossible.", details={"cause": str(exc)}) from exc


def supprimer_messages(conversation_id: str) -> int:
    """Vide l'historique sans supprimer la conversation ni ses réglages. Retourne le nombre effacé."""
    exiger_conversation(conversation_id)
    supprimes = execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    execute("UPDATE conversations SET maj_le = ? WHERE id = ?", (maintenant(), conversation_id))
    logger.debug("{} message(s) supprimé(s) dans {}", supprimes, conversation_id)
    return supprimes
