"""Politique de quotas et de validation du type MIME — pas de disque, pas de base ici."""

from __future__ import annotations

import pytest

from backend.fichiers import politique
from backend.fichiers.erreurs import FichierTropVolumineux, QuotaConversationDepasse, TypeMimeRefuse


def test_type_mime_liste_est_accepte() -> None:
    assert politique.valider_type_mime("text/plain") == "text/plain"


def test_type_mime_avec_parametres_est_normalise() -> None:
    assert politique.valider_type_mime("text/plain; charset=utf-8") == "text/plain"


def test_type_mime_absent_est_refuse() -> None:
    with pytest.raises(TypeMimeRefuse):
        politique.valider_type_mime(None)


def test_type_mime_hors_liste_est_refuse() -> None:
    with pytest.raises(TypeMimeRefuse):
        politique.valider_type_mime("application/x-msdownload")


def test_extension_derive_du_mime() -> None:
    assert politique.extension_pour("image/png") == ".png"


def test_taille_sous_le_plafond_est_acceptee() -> None:
    politique.verifier_taille_fichier(politique.TAILLE_MAX_FICHIER_OCTETS)  # ne doit pas lever


def test_taille_au_dela_du_plafond_est_refusee() -> None:
    with pytest.raises(FichierTropVolumineux):
        politique.verifier_taille_fichier(politique.TAILLE_MAX_FICHIER_OCTETS + 1)


def test_cumul_sous_le_plafond_est_accepte() -> None:
    politique.verifier_quota_cumule(0, politique.TAILLE_MAX_CUMULEE_OCTETS)  # ne doit pas lever


def test_cumul_au_dela_du_plafond_est_refuse() -> None:
    with pytest.raises(QuotaConversationDepasse):
        politique.verifier_quota_cumule(politique.TAILLE_MAX_CUMULEE_OCTETS, 1)
