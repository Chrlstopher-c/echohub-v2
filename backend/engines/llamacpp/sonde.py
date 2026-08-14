"""Sonde llama.cpp — script autonome, exécuté dans un process jetable.

N'IMPORTE RIEN DU BACKEND, par construction : ce fichier doit rester exécutable par n'importe quel
interpréteur où `llama_cpp` est installé, y compris hors du `sys.path` du projet.

Ce qu'il mesure, et pourquoi : le wheel PyPI de `llama-cpp-python` est CPU-only. Une image dont la
recompilation CUDA a échoué produit un backend qui « fonctionne » sans jamais toucher le GPU —
panne silencieuse, la pire catégorie. La preuve recherchée est celle du DOCKER-BUILD-LOG de la
v1 : `CUDA : ARCHS = 860,1200 | FORCE_CUBLAS = 1`.

Sortie : une ligne unique sur stdout préfixée par la sentinelle, contenant du JSON. Le préfixe
existe parce que la bibliothèque native écrit ses propres messages sur les mêmes flux.
"""

from __future__ import annotations

import json
import re
import sys

# Doit rester identique à SENTINELLE_SONDE de backend/engines/_sonde.py.
SENTINELLE = "__ECHOHUB_SONDE__"

# Longueur conservée de l'info système : de quoi diagnostiquer, pas de quoi noyer un journal.
MAX_INFO = 2_000

_MOTIF_ARCHS = re.compile(r"ARCHS\s*=\s*([0-9,\s]+)")
_MOTIF_CUBLAS = re.compile(r"FORCE_CUBLAS\s*=\s*(\d+)")


def _architectures(info: str) -> list[str]:
    """Traduit les codes CMake rapportés par le binaire en noms d'architectures lisibles.

    llama.cpp imprime les codes tels que CMake les lui a passés (860, 1200) ; `sm_86` et `sm_120`
    sont les mêmes valeurs sous la forme employée partout ailleurs (torch, documentation NVIDIA).
    """
    correspondance = _MOTIF_ARCHS.search(info)
    if correspondance is None:
        return []
    architectures: list[str] = []
    for code in correspondance.group(1).split(","):
        nettoye = code.strip()
        if nettoye.isdigit():
            architectures.append(f"sm_{int(nettoye) // 10}")
    return architectures


def _force_cublas(info: str) -> bool | None:
    correspondance = _MOTIF_CUBLAS.search(info)
    if correspondance is None:
        return None
    return correspondance.group(1) != "0"


def _info_systeme(module: object) -> str:
    """Chaîne de capacités du binaire. Le backend doit être initialisé pour qu'elle soit peuplée."""
    initialiser = getattr(module, "llama_backend_init", None)
    if callable(initialiser):
        initialiser()
    lire = getattr(module, "llama_print_system_info", None)
    if not callable(lire):
        return ""
    brut = lire()
    return brut.decode("utf-8", errors="replace") if isinstance(brut, bytes) else str(brut)


def diagnostiquer() -> dict[str, object]:
    """Constat complet, y compris en cas d'échec : un diagnostic vide serait ininterprétable."""
    resultat: dict[str, object] = {
        "importable": False,
        "version": None,
        "architectures_gpu": [],
        "force_cublas": None,
        "offload_gpu": None,
        "info_systeme": "",
        "erreur": None,
        "type_erreur": None,
    }
    try:
        import llama_cpp
    except BaseException as exc:  # noqa: BLE001 - une bibliothèque native peut lever hors Exception
        resultat["erreur"] = str(exc)[:500]
        resultat["type_erreur"] = type(exc).__name__
        return resultat

    resultat["importable"] = True
    resultat["version"] = getattr(llama_cpp, "__version__", None)
    try:
        info = _info_systeme(llama_cpp)
        resultat["info_systeme"] = info[:MAX_INFO]
        resultat["architectures_gpu"] = _architectures(info)
        resultat["force_cublas"] = _force_cublas(info)
        supporte = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        resultat["offload_gpu"] = bool(supporte()) if callable(supporte) else None
    except BaseException as exc:  # noqa: BLE001 - idem : l'appel natif peut échouer brutalement
        resultat["erreur"] = str(exc)[:500]
        resultat["type_erreur"] = type(exc).__name__
    return resultat


def main() -> int:
    charge = diagnostiquer()
    sys.stdout.write(f"\n{SENTINELLE}{json.dumps(charge, ensure_ascii=False)}\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
