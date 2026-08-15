"""Preuves du balayage du bac — c'est lui qui fait qu'un fichier produit par le modèle entre dans
le même magasin qu'une pièce jointe (plan d'exécution, 2.1), avec `origine='modele'`.
"""

from __future__ import annotations

from pathlib import Path

from backend.chat.modeles import ResumeConversation
from backend.fichiers import TAILLE_MAX_FICHIER_OCTETS, chemin_disque, lire_fichier
from backend.outils import balayage_bac


def test_etat_bac_rend_ensemble_vide_si_le_dossier_nexiste_pas(tmp_path: Path) -> None:
    assert balayage_bac.etat_bac(tmp_path / "jamais-cree") == frozenset()


def test_balayer_et_enregistrer_ajoute_le_fichier_avec_origine_modele(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    avant = balayage_bac.etat_bac(racine_bac)
    racine_bac.mkdir(parents=True, exist_ok=True)
    (racine_bac / "resultat.csv").write_text("a,b\n1,2\n")

    fichiers = balayage_bac.balayer_et_enregistrer(conversation.id, racine_bac, avant)

    assert len(fichiers) == 1
    fichier = fichiers[0]
    assert fichier.origine == "modele"
    assert fichier.nom_affiche == "resultat.csv"
    assert fichier.conversation_id == conversation.id
    assert chemin_disque(fichier).read_text() == "a,b\n1,2\n"
    # Retrouvable par la même route que n'importe quel autre fichier du magasin.
    assert lire_fichier(fichier.id).id == fichier.id


def test_balayer_et_enregistrer_ignore_les_fichiers_deja_presents_avant(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    racine_bac.mkdir(parents=True, exist_ok=True)
    (racine_bac / "deja_la.txt").write_text("préexistant")
    avant = balayage_bac.etat_bac(racine_bac)  # pris APRÈS l'écriture : rien de nouveau ensuite

    fichiers = balayage_bac.balayer_et_enregistrer(conversation.id, racine_bac, avant)

    assert fichiers == []


def test_fichier_trop_gros_est_ignore_sans_bloquer_les_autres(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    racine_bac.mkdir(parents=True, exist_ok=True)
    avant = balayage_bac.etat_bac(racine_bac)
    (racine_bac / "gros.bin").write_bytes(b"\0" * (TAILLE_MAX_FICHIER_OCTETS + 1))
    (racine_bac / "petit.txt").write_text("ok")

    fichiers = balayage_bac.balayer_et_enregistrer(conversation.id, racine_bac, avant)

    noms = {f.nom_affiche for f in fichiers}
    assert noms == {"petit.txt"}, "le fichier trop gros est ignoré, le petit doit quand même passer"


def test_type_mime_hors_liste_blanche_est_ignore(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    racine_bac.mkdir(parents=True, exist_ok=True)
    avant = balayage_bac.etat_bac(racine_bac)
    (racine_bac / "binaire.dat").write_bytes(b"\x00\x01")  # extension sans type MIME deviné

    fichiers = balayage_bac.balayer_et_enregistrer(conversation.id, racine_bac, avant)

    assert fichiers == []
