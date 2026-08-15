"""Orchestration `deposer_fichier` / `lire_fichier` — quotas AVANT écriture, MIME jamais deviné."""

from __future__ import annotations

import hashlib

import pytest

from backend.chat.modeles import ResumeConversation
from backend.core import ConversationIntrouvable
from backend.fichiers import depot, politique, service, stockage
from backend.fichiers.erreurs import FichierIntrouvable, FichierTropVolumineux, QuotaConversationDepasse, TypeMimeRefuse


def test_deposer_fichier_enregistre_reference_et_empreinte(conversation: ResumeConversation) -> None:
    octets = b"contenu de test"

    fichier = service.deposer_fichier(
        conversation.id,
        nom_fourni="notes.txt",
        type_mime_declare="text/plain",
        octets=octets,
        origine="utilisateur",
    )

    assert fichier.empreinte_sha256 == hashlib.sha256(octets).hexdigest()
    assert fichier.taille_octets == len(octets)
    assert fichier.type_mime == "text/plain"
    releve = depot.lire_fichier(fichier.id)
    assert releve is not None
    assert releve.chemin_relatif == fichier.chemin_relatif
    assert stockage.chemin_absolu(fichier.chemin_relatif).read_bytes() == octets


def test_conversation_inconnue_est_refusee(base: object) -> None:
    with pytest.raises(ConversationIntrouvable):
        service.deposer_fichier(
            "inconnue",
            nom_fourni="a.txt",
            type_mime_declare="text/plain",
            octets=b"x",
            origine="utilisateur",
        )


def test_type_mime_hors_liste_est_refuse(conversation: ResumeConversation) -> None:
    with pytest.raises(TypeMimeRefuse):
        service.deposer_fichier(
            conversation.id,
            nom_fourni="script.exe",
            type_mime_declare="application/x-msdownload",
            octets=b"x",
            origine="utilisateur",
        )


def test_extension_disque_derive_du_mime_pas_du_nom_fourni(conversation: ResumeConversation) -> None:
    """Le nom fourni ment sur son extension : le fichier écrit doit suivre le MIME validé, pas lui."""
    fichier = service.deposer_fichier(
        conversation.id,
        nom_fourni="image_deguisee.txt",
        type_mime_declare="image/png",
        octets=b"\x89PNG\r\n\x1a\n",
        origine="utilisateur",
    )

    assert fichier.chemin_relatif.endswith(".png")
    assert fichier.nom_affiche == "image_deguisee.txt"


def test_origine_modele_est_acceptee(conversation: ResumeConversation) -> None:
    fichier = service.deposer_fichier(
        conversation.id,
        nom_fourni="sortie.json",
        type_mime_declare="application/json",
        octets=b"{}",
        origine="modele",
    )
    assert fichier.origine == "modele"


def test_fichier_trop_volumineux_est_refuse(conversation: ResumeConversation, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(politique, "TAILLE_MAX_FICHIER_OCTETS", 4)
    with pytest.raises(FichierTropVolumineux):
        service.deposer_fichier(
            conversation.id,
            nom_fourni="a.txt",
            type_mime_declare="text/plain",
            octets=b"12345",
            origine="utilisateur",
        )


def test_quota_cumule_est_refuse_au_second_depot(
    conversation: ResumeConversation, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(politique, "TAILLE_MAX_CUMULEE_OCTETS", 10)
    service.deposer_fichier(
        conversation.id, nom_fourni="a.txt", type_mime_declare="text/plain", octets=b"12345", origine="utilisateur"
    )

    with pytest.raises(QuotaConversationDepasse):
        service.deposer_fichier(
            conversation.id,
            nom_fourni="b.txt",
            type_mime_declare="text/plain",
            octets=b"12345678",
            origine="utilisateur",
        )


def test_echec_de_quota_ne_laisse_aucune_trace(
    conversation: ResumeConversation, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Les quotas sont vérifiés AVANT toute écriture : un refus ne doit rien laisser derrière lui."""
    monkeypatch.setattr(politique, "TAILLE_MAX_FICHIER_OCTETS", 1)

    with pytest.raises(FichierTropVolumineux):
        service.deposer_fichier(
            conversation.id, nom_fourni="a.txt", type_mime_declare="text/plain", octets=b"12345", origine="utilisateur"
        )

    assert depot.lister_fichiers(conversation.id) == []
    assert not stockage.dossier_fichiers(conversation.id).exists()


def test_lire_fichier_absent_leve_fichier_introuvable(base: object) -> None:
    with pytest.raises(FichierIntrouvable):
        service.lire_fichier("inconnu")
