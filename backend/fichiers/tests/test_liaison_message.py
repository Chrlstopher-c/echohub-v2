"""Liaison pièce jointe <-> message (plan d'exécution, section 2.2.1) : une RELATION, pas un champ.

`lier_fichiers_au_message` referme le lien une fois le message persisté (le composeur dépose la
pièce AVANT que le message n'existe) ; `pieces_pour_messages` relit ce lien en une seule requête
groupée, pour tout un historique de conversation.
"""

from __future__ import annotations

from backend.chat.depot import ajouter_message
from backend.chat.modeles import ResumeConversation
from backend.fichiers import depot, service


def _deposer(conversation_id: str, nom: str) -> str:
    fichier = service.deposer_fichier(
        conversation_id,
        nom_fourni=nom,
        type_mime_declare="image/png",
        octets=b"\x89PNG\r\n\x1a\nfaux-contenu",
        origine="utilisateur",
    )
    return fichier.id


def test_lier_fichiers_au_message_referme_le_lien(conversation: ResumeConversation) -> None:
    fichier_id = _deposer(conversation.id, "capture.png")
    message = ajouter_message(conversation.id, role="user", contenu="Regarde")

    service.lier_fichiers_au_message(conversation.id, [fichier_id], message.id)

    releve = depot.lire_fichier(fichier_id)
    assert releve is not None
    assert releve.message_id == message.id


def test_lier_fichiers_au_message_ignore_un_fichier_etranger(conversation: ResumeConversation) -> None:
    """Un identifiant d'une AUTRE conversation ne doit jamais être rattaché ici — pas d'exception,
    pas d'écriture : le texte du message doit pouvoir partir même si une pièce jointe est invalide."""
    from backend.chat.depot import creer_conversation
    from backend.chat.modeles import ReglagesConversation

    autre = creer_conversation("Autre conversation", None, ReglagesConversation())
    fichier_etranger = _deposer(autre.id, "ailleurs.png")
    message = ajouter_message(conversation.id, role="user", contenu="Regarde")

    service.lier_fichiers_au_message(conversation.id, [fichier_etranger], message.id)

    releve = depot.lire_fichier(fichier_etranger)
    assert releve is not None
    assert releve.message_id is None


def test_lier_fichiers_au_message_ignore_un_identifiant_inconnu(conversation: ResumeConversation) -> None:
    message = ajouter_message(conversation.id, role="user", contenu="Regarde")
    # Ne doit pas lever : un identifiant forgé ou périmé ne fait pas échouer l'envoi du message.
    service.lier_fichiers_au_message(conversation.id, ["inconnu-forge"], message.id)


def test_pieces_pour_messages_groupe_par_message_en_une_requete(conversation: ResumeConversation) -> None:
    message_a = ajouter_message(conversation.id, role="user", contenu="Premier")
    message_b = ajouter_message(conversation.id, role="user", contenu="Second", parent_id=message_a.id)

    fichier_a1 = _deposer(conversation.id, "a1.png")
    fichier_a2 = _deposer(conversation.id, "a2.png")
    fichier_b = _deposer(conversation.id, "b.png")
    service.lier_fichiers_au_message(conversation.id, [fichier_a1, fichier_a2], message_a.id)
    service.lier_fichiers_au_message(conversation.id, [fichier_b], message_b.id)

    groupes = service.pieces_pour_messages([message_a.id, message_b.id])

    assert {f.id for f in groupes[message_a.id]} == {fichier_a1, fichier_a2}
    assert {f.id for f in groupes[message_b.id]} == {fichier_b}


def test_pieces_pour_messages_absent_du_dictionnaire_pour_un_message_sans_piece(
    conversation: ResumeConversation,
) -> None:
    message = ajouter_message(conversation.id, role="user", contenu="Rien de joint")
    groupes = service.pieces_pour_messages([message.id])
    assert message.id not in groupes


def test_pieces_pour_messages_sur_liste_vide_rend_un_dictionnaire_vide() -> None:
    """Garde `if not message_ids` de `depot.lister_par_messages` : SQLite accepte `IN ()` (toujours
    faux, donc `{}` de toute façon), la garde n'est donc qu'un évitement de requête — vérifié en
    la retirant : le test reste vert, elle est documentée comme optimisation et non correction."""
    assert service.pieces_pour_messages([]) == {}
