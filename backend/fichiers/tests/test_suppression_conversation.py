"""Test d'assemblage — la suppression d'une conversation supprime son dossier de fichiers.

C'est la preuve que le domaine `fichiers` est réellement appelé par `backend.chat.depot`, et pas
seulement complet et testé en vase clos (règle d'assemblage, section 2.7 du plan d'exécution).
"""

from __future__ import annotations

from backend.chat.depot import supprimer_conversation
from backend.chat.modeles import ResumeConversation
from backend.fichiers import depot, service, stockage


def test_supprimer_conversation_supprime_le_dossier_disque(conversation: ResumeConversation) -> None:
    service.deposer_fichier(
        conversation.id,
        nom_fourni="a.txt",
        type_mime_declare="text/plain",
        octets=b"contenu",
        origine="utilisateur",
    )
    dossier_conversation = stockage.racine_conversations() / conversation.id
    assert dossier_conversation.exists()

    supprimer_conversation(conversation.id)

    assert not dossier_conversation.exists()


def test_supprimer_conversation_supprime_les_lignes_en_base(conversation: ResumeConversation) -> None:
    fichier = service.deposer_fichier(
        conversation.id,
        nom_fourni="a.txt",
        type_mime_declare="text/plain",
        octets=b"contenu",
        origine="utilisateur",
    )

    supprimer_conversation(conversation.id)

    assert depot.lire_fichier(fichier.id) is None


def test_supprimer_conversation_sans_fichier_ne_leve_pas(conversation: ResumeConversation) -> None:
    """Aucun fichier déposé : la branche disque ne doit pas transformer une suppression normale en échec."""
    supprimer_conversation(conversation.id)
