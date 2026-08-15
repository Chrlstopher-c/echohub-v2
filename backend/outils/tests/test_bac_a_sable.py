"""Preuves du lanceur confiné (`bac_a_sable.py`) — portables, sans exiger root.

Le changement d'utilisateur (`setuid`/`setgid`) ne s'active QUE si l'appelant est root
(`os.getuid() == 0`) : en développement, ces tests tournent déjà sous un utilisateur non
privilégié, la bascule est sautée par construction (voir `bac_a_sable._preexec`). La preuve que
`os.getuid()` rend une valeur non nulle APRÈS un `setuid` réel n'est donc démontrable qu'en
conteneur, en root — c'est le script `scripts/preuves_bac_a_sable.py`, preuve (a) du rapport de lot.

Ce qui EST démontrable ici, portable, parce que les `RLIMIT_*` s'appliquent quel que soit
l'utilisateur courant : le temps processeur (b) et la taille de fichier (c).
"""

from __future__ import annotations

from pathlib import Path

from backend.outils import bac_a_sable


def test_boucle_infinie_meurt_sur_la_limite_de_temps_processeur(racine_bac: Path) -> None:
    """(b) — `while True: pass` est tué par `RLIMIT_CPU`, bien avant le filet de sécurité."""
    plafond_test_secondes = 2  # abaissé pour que le test reste rapide ; la mécanique est la même.
    ancien = bac_a_sable.LIMITE_CPU_SECONDES
    try:
        bac_a_sable.LIMITE_CPU_SECONDES = plafond_test_secondes
        resultat = bac_a_sable.executer_code_confine("while True: pass", racine_bac)
    finally:
        bac_a_sable.LIMITE_CPU_SECONDES = ancien

    assert resultat.code_retour != 0, "le processus doit avoir été tué, pas terminé normalement"
    assert not resultat.tue_par_filet_securite, "doit mourir sur RLIMIT_CPU, pas sur le filet de sécurité"
    # Le plafond FIXÉ pour cette preuve est le filet de sécurité (20 s) : la mort doit intervenir
    # nettement avant, ce qui prouve que c'est bien la rlimit qui a agi et non le filet lui-même.
    assert resultat.duree_s < bac_a_sable.TIMEOUT_SECURITE_SECONDES


def test_ecriture_dun_fichier_dun_gigaoctet_echoue(racine_bac: Path) -> None:
    """(c) — l'écriture est bloquée par `RLIMIT_FSIZE`, bien avant d'atteindre 1 Go."""
    code = (
        "f = open('gros.bin', 'wb')\n"
        "morceau = b'0' * (1024 * 1024)\n"
        "for _ in range(1024):\n"  # 1024 Mio visés, très au-delà de la limite de 64 Mio.
        "    f.write(morceau)\n"
        "    f.flush()\n"
    )
    resultat = bac_a_sable.executer_code_confine(code, racine_bac)

    assert resultat.code_retour != 0, "l'écriture doit échouer, pas se terminer normalement"
    chemin_ecrit = racine_bac / "gros.bin"
    if chemin_ecrit.exists():
        assert chemin_ecrit.stat().st_size < 1024 * 1024 * 1024, "jamais 1 Go effectivement écrit"
        assert chemin_ecrit.stat().st_size <= bac_a_sable.LIMITE_TAILLE_FICHIER_OCTETS


def test_deux_conversations_ecrivent_dans_deux_dossiers_differents(racine_bac: Path, tmp_path: Path) -> None:
    """(e) — deux bacs distincts, un par conversation, ne se mélangent jamais."""
    autre_bac = tmp_path / "autre-conversation" / "bac"

    bac_a_sable.executer_code_confine("open('depuis_a.txt', 'w').write('a')", racine_bac)
    bac_a_sable.executer_code_confine("open('depuis_b.txt', 'w').write('b')", autre_bac)

    assert (racine_bac / "depuis_a.txt").exists()
    assert (autre_bac / "depuis_b.txt").exists()
    assert not (racine_bac / "depuis_b.txt").exists()
    assert not (autre_bac / "depuis_a.txt").exists()


def test_preparer_bac_cree_le_dossier_sil_est_absent(tmp_path: Path) -> None:
    cible = tmp_path / "conv-x" / "bac"
    assert not cible.exists()
    bac_a_sable.preparer_bac(cible)
    assert cible.is_dir()


def test_limites_reelles_texte_narrive_pas_a_promettre_plus_quautorise() -> None:
    """Le texte destiné à l'interface (L3) ne doit jamais annoncer une garantie fausse."""
    texte = bac_a_sable.LIMITES_REELLES_TEXTE
    assert "non privilégié" in texte
    assert "réseau n'est pas coupé" in texte
    assert "bac de cette conversation" in texte
