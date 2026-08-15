"""Persistance SQL du domaine `fichiers` — table `fichiers_conversation`."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.chat.modeles import ResumeConversation
from backend.fichiers import depot
from backend.fichiers.modeles import FichierConversation


def _fichier(conversation_id: str, **surcharges: object) -> FichierConversation:
    valeurs = {
        "id": "fichier-1",
        "conversation_id": conversation_id,
        "message_id": None,
        "origine": "utilisateur",
        "nom_affiche": "notes.txt",
        "chemin_relatif": f"{conversation_id}/fichiers/fichier-1.txt",
        "type_mime": "text/plain",
        "taille_octets": 7,
        "empreinte_sha256": "abc123",
        "cree_le": datetime.now(timezone.utc),
    }
    valeurs.update(surcharges)
    return FichierConversation.model_validate(valeurs)


def test_enregistrer_puis_lire_rend_la_meme_reference(conversation: ResumeConversation) -> None:
    fichier = _fichier(conversation.id)
    depot.enregistrer_fichier(fichier)

    relu = depot.lire_fichier(fichier.id)

    assert relu is not None
    assert relu.id == fichier.id
    assert relu.chemin_relatif == fichier.chemin_relatif
    assert relu.empreinte_sha256 == fichier.empreinte_sha256
    assert relu.origine == "utilisateur"


def test_lire_fichier_absent_rend_none(conversation: ResumeConversation) -> None:
    assert depot.lire_fichier("inconnu") is None


def test_lister_fichiers_ordonne_par_date(conversation: ResumeConversation) -> None:
    depot.enregistrer_fichier(_fichier(conversation.id, id="f1", cree_le=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    depot.enregistrer_fichier(_fichier(conversation.id, id="f2", cree_le=datetime(2026, 1, 2, tzinfo=timezone.utc)))

    fichiers = depot.lister_fichiers(conversation.id)

    assert [f.id for f in fichiers] == ["f1", "f2"]


def test_taille_cumulee_sans_fichier_est_zero(conversation: ResumeConversation) -> None:
    assert depot.taille_cumulee(conversation.id) == 0


def test_taille_cumulee_somme_les_fichiers_de_la_conversation(conversation: ResumeConversation) -> None:
    depot.enregistrer_fichier(_fichier(conversation.id, id="f1", taille_octets=10))
    depot.enregistrer_fichier(_fichier(conversation.id, id="f2", taille_octets=25))

    assert depot.taille_cumulee(conversation.id) == 35


def test_taille_cumulee_ignore_les_autres_conversations(
    conversation: ResumeConversation,
) -> None:
    from backend.chat.depot import creer_conversation
    from backend.chat.modeles import ReglagesConversation

    autre = creer_conversation("Autre", None, ReglagesConversation())
    depot.enregistrer_fichier(_fichier(conversation.id, id="f1", taille_octets=10))
    depot.enregistrer_fichier(_fichier(autre.id, id="f2", taille_octets=999))

    assert depot.taille_cumulee(conversation.id) == 10
