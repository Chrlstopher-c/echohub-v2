#!/usr/bin/env python3
"""Preuves du lot L2, à exécuter DANS LE CONTENEUR, en root — c'est la condition de la preuve (a).

Exerce directement `backend.outils.bac_a_sable.executer_code_confine`, le même code que l'outil
`executer_python` appelle en production (`backend/outils/executer_python.py`). Rien n'est simulé :
c'est un vrai `fork`+`exec`, un vrai `setuid`, de vraies `rlimit`.

Usage : PYTHONPATH=/app python3 /app/docker/preuves_bac_a_sable.py

Sort 0 et affiche ce qui a été mesuré si les cinq preuves passent ; sort 1 et dit laquelle a échoué
sinon. N'écrit rien de permanent : les répertoires de preuve sont sous un `tempfile.mkdtemp()`,
supprimés en fin de script.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/app")

from backend.outils import bac_a_sable  # noqa: E402


def echec(message: str) -> None:
    print(f"ÉCHEC : {message}")
    sys.exit(1)


def preuve_a_uid_non_nul(racine: Path) -> None:
    print("\n--- (a) os.getuid() dans le processus confiné doit être != 0 ---")
    if os.getuid() != 0:
        echec("ce script doit tourner en root pour être une preuve : la bascule n'aurait rien à prouver.")
    bac = racine / "conv-preuve-a" / "bac"
    resultat = bac_a_sable.executer_code_confine("import os; print(os.getuid())", bac)
    print(f"appelant : uid={os.getuid()} (root, attendu) | processus confiné : {resultat.sortie.strip()!r}")
    if resultat.code_retour != 0:
        echec(f"le processus confiné n'a pas pu s'exécuter : {resultat.erreur}")
    uid_confine = int(resultat.sortie.strip())
    if uid_confine == 0:
        echec("le processus confiné a rendu uid=0 : la bascule setuid n'a pas eu lieu.")
    if uid_confine != bac_a_sable.SANDBOX_UID:
        echec(f"uid confiné {uid_confine} != SANDBOX_UID {bac_a_sable.SANDBOX_UID}")
    print(f"OK : uid confiné = {uid_confine} (SANDBOX_UID), non nul, non root.")


def preuve_b_rlimit_cpu(racine: Path) -> None:
    print("\n--- (b) une boucle infinie meurt sur RLIMIT_CPU, avant le filet de sécurité ---")
    bac = racine / "conv-preuve-b" / "bac"
    resultat = bac_a_sable.executer_code_confine("while True: pass", bac)
    print(f"code_retour={resultat.code_retour} duree_s={resultat.duree_s:.2f} "
          f"tue_par_filet_securite={resultat.tue_par_filet_securite} "
          f"(plafond RLIMIT_CPU={bac_a_sable.LIMITE_CPU_SECONDES}s, "
          f"filet de sécurité={bac_a_sable.TIMEOUT_SECURITE_SECONDES}s)")
    if resultat.tue_par_filet_securite:
        echec("mort sur le filet de sécurité, pas sur RLIMIT_CPU : la rlimit n'a pas agi.")
    if resultat.code_retour == 0:
        echec("le processus s'est terminé normalement : la boucle infinie n'a pas été tuée.")
    if resultat.duree_s >= bac_a_sable.TIMEOUT_SECURITE_SECONDES:
        echec("mort trop tard : au-delà du plafond fixé pour cette preuve.")
    print(f"OK : tué en {resultat.duree_s:.2f}s, sous le plafond de {bac_a_sable.TIMEOUT_SECURITE_SECONDES}s.")


def preuve_c_gigaoctet(racine: Path) -> None:
    print("\n--- (c) l'écriture d'un fichier de 1 Go échoue ---")
    bac = racine / "conv-preuve-c" / "bac"
    code = (
        "f = open('gros.bin', 'wb')\n"
        "morceau = b'0' * (1024 * 1024)\n"
        "for _ in range(1024):\n"
        "    f.write(morceau)\n"
        "    f.flush()\n"
    )
    resultat = bac_a_sable.executer_code_confine(code, bac)
    chemin = bac / "gros.bin"
    taille = chemin.stat().st_size if chemin.exists() else 0
    print(f"code_retour={resultat.code_retour} taille_ecrite={taille} octets "
          f"(limite RLIMIT_FSIZE={bac_a_sable.LIMITE_TAILLE_FICHIER_OCTETS} octets)")
    if resultat.code_retour == 0:
        echec("le processus s'est terminé normalement : l'écriture de 1 Go n'a pas été bloquée.")
    if taille >= 1024 * 1024 * 1024:
        echec("le fichier a atteint 1 Go : RLIMIT_FSIZE n'a pas agi.")
    print(f"OK : écriture arrêtée à {taille} octets, très en dessous de 1 Go.")


def preuve_d_hors_bac(racine: Path) -> None:
    print("\n--- (d) une écriture hors du bac est refusée ---")
    bac = racine / "conv-preuve-d" / "bac"
    cible = racine / "hors_bac_refuse.txt"  # au-dessus du bac, dans un dossier resté root:root
    code = f"open({str(cible)!r}, 'w').write('fuite')"
    resultat = bac_a_sable.executer_code_confine(code, bac)
    print(f"code_retour={resultat.code_retour} cible={cible} existe_apres={cible.exists()}")
    print(f"erreur du processus confiné : {resultat.erreur.strip()[:200]}")
    if cible.exists():
        echec("le fichier a été écrit HORS du bac : l'écriture aurait dû être refusée.")
    if resultat.code_retour == 0:
        echec("le processus s'est terminé sans erreur alors que l'écriture aurait dû échouer.")
    print("OK : écriture hors du bac refusée (permissions Unix, dossier resté root:root).")


def preuve_e_deux_conversations(racine: Path) -> None:
    print("\n--- (e) deux conversations écrivent dans deux dossiers différents ---")
    bac_x = racine / "conv-preuve-e-x" / "bac"
    bac_y = racine / "conv-preuve-e-y" / "bac"
    bac_a_sable.executer_code_confine("open('depuis_x.txt', 'w').write('x')", bac_x)
    bac_a_sable.executer_code_confine("open('depuis_y.txt', 'w').write('y')", bac_y)
    print(f"bac X = {bac_x} -> contient : {sorted(p.name for p in bac_x.iterdir())}")
    print(f"bac Y = {bac_y} -> contient : {sorted(p.name for p in bac_y.iterdir())}")
    if not (bac_x / "depuis_x.txt").exists() or not (bac_y / "depuis_y.txt").exists():
        echec("un des deux fichiers attendus est absent.")
    if (bac_x / "depuis_y.txt").exists() or (bac_y / "depuis_x.txt").exists():
        echec("un fichier a fui d'un bac vers l'autre.")
    print("OK : deux bacs distincts, aucune fuite entre conversations.")


def main() -> None:
    racine = Path(tempfile.mkdtemp(prefix="preuves-l2-"))
    print(f"Répertoire de preuve (temporaire) : {racine}")
    try:
        preuve_a_uid_non_nul(racine)
        preuve_b_rlimit_cpu(racine)
        preuve_c_gigaoctet(racine)
        preuve_d_hors_bac(racine)
        preuve_e_deux_conversations(racine)
    finally:
        shutil.rmtree(racine, ignore_errors=True)
    print("\n=== Les cinq preuves (a) à (e) sont passées. ===")


if __name__ == "__main__":
    main()
