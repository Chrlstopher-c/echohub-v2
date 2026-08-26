"""Ce que ces tests empêchent : qu'un fichier produit par le modèle devienne inaccessible.

Mesuré le 2026-08-26 sur un fil réel. Le modèle écrit trois fichiers assembleur — `hello_x86_64.s`,
`hello_arm64.S`, `hello_mips.s` — et le journal répond trois fois :

    Fichier hello_x86_64.s écrit mais non déposé dans le magasin :
    Type MIME refusé : (absent) -> Type de fichier non pris en charge.

`mimetypes.guess_type` ne connaît pas `.s`. Les fichiers existaient dans le bac, l'utilisateur n'en
a vu aucun, et le travail annoncé comme fait était introuvable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.outils.fichiers_bac import _type_mime_devine


def _ecrire(dossier: Path, nom: str, octets: bytes) -> Path:
    chemin = dossier / nom
    chemin.write_bytes(octets)
    return chemin


@pytest.mark.parametrize("nom", ["hello_x86_64.s", "hello_arm64.S", "main.rs", "index.ts", "build.sh"])
def test_les_extensions_de_code_source_sont_acceptees(tmp_path: Path, nom: str) -> None:
    """Le cas réel : trois de ces extensions ont produit trois fichiers perdus."""
    cible = _ecrire(tmp_path, nom, b".globl main\nmain:\n    ret\n")
    assert _type_mime_devine(nom, cible) == "text/plain"


def test_un_type_connu_de_mimetypes_est_conserve(tmp_path: Path) -> None:
    """La détection standard reste prioritaire : on ne la remplace pas, on la complète."""
    cible = _ecrire(tmp_path, "page.html", b"<!doctype html><p>x</p>")
    assert _type_mime_devine("page.html", cible) == "text/html"


def test_un_binaire_a_extension_inconnue_reste_refuse(tmp_path: Path) -> None:
    """Le garde-fou. L'extension oriente, le CONTENU tranche — sinon la liste blanche ne sert plus.

    Des octets nuls ne se décodent pas en UTF-8 : le fichier est refusé, et c'est voulu.
    """
    cible = _ecrire(tmp_path, "donnees.bizarre", b"\x00\x01\x02\xff\xfe binaire")
    assert _type_mime_devine("donnees.bizarre", cible) is None


def test_un_fichier_sans_extension_est_accepte_s_il_est_du_texte(tmp_path: Path) -> None:
    """`Makefile`, `Dockerfile`, `LICENSE` : sans extension, mais parfaitement lisibles."""
    cible = _ecrire(tmp_path, "Makefile", b"all:\n\tgcc -o hello hello.c\n")
    assert _type_mime_devine("Makefile", cible) == "text/plain"


def test_un_fichier_illisible_ne_fait_pas_echouer_la_detection(tmp_path: Path) -> None:
    """Un chemin disparu entre l'écriture et la lecture rend `None`, jamais une exception."""
    assert _type_mime_devine("absent.s", tmp_path / "absent.s") is None
