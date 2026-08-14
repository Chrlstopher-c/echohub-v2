"""Mesure de la mémoire système — totale et réellement disponible.

`disponible` et non `libre` : la mémoire libre au sens strict exclut le cache page, qui est
récupérable. C'est `disponible` qui dit ce qu'un chargement de modèle peut réellement prendre.

Sous WSL2, ces valeurs sont celles de la VM, pas de l'hôte Windows — la VM est plafonnée par
défaut à environ 50 % de la RAM physique. C'est bien le chiffre utile : la VM est ce dans quoi le
processus s'exécute. La contrainte correspondante est portée par `plateforme.py`.

Un échec de mesure retourne `None`, jamais zéro : « pas mesuré » et « rien de disponible » mènent
à des plans différents, les confondre ferait planifier un offload CPU à l'aveugle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from backend.system.modeles import Memoire

_CHEMIN_MEMINFO = Path("/proc/meminfo")

# `/proc/meminfo` fait une cinquantaine de lignes : borne haute pour ne pas lire un flux anormal.
_LIGNES_MAX_MEMINFO = 200

_CLES_MEMINFO = ("MemTotal", "MemAvailable")

_psutil: Any
try:
    import psutil as _module_psutil

    _psutil = _module_psutil
except ImportError:  # dépendance déclarée mais environnement possiblement incomplet
    _psutil = None


def _via_psutil() -> Memoire | None:
    """Chemin nominal, multiplateforme."""
    if _psutil is None:
        logger.debug("psutil indisponible : repli sur /proc/meminfo.")
        return None
    try:
        virtuelle = _psutil.virtual_memory()
        return Memoire(totale_octets=int(virtuelle.total), disponible_octets=int(virtuelle.available))
    except Exception as exc:  # psutil remonte des erreurs système variées selon la plateforme
        logger.warning("Lecture mémoire via psutil échouée : {}", exc)
        return None


def _kilo_octets(reste: str) -> int | None:
    """`/proc/meminfo` exprime ses valeurs en kB (kibioctets, malgré l'unité affichée)."""
    tete = reste.strip().split(maxsplit=1)[0] if reste.strip() else ""
    return int(tete) * 1024 if tete.isdigit() else None


def _via_proc_meminfo() -> Memoire | None:
    """Repli Linux quand psutil est absent ou défaillant."""
    try:
        lignes = _CHEMIN_MEMINFO.read_text(encoding="utf-8").splitlines()[:_LIGNES_MAX_MEMINFO]
    except OSError as exc:
        logger.warning("Mémoire non mesurable, /proc/meminfo illisible : {}", exc)
        return None

    valeurs: dict[str, int] = {}
    for ligne in lignes:
        cle, _, reste = ligne.partition(":")
        if cle in _CLES_MEMINFO:
            octets = _kilo_octets(reste)
            if octets is not None:
                valeurs[cle] = octets

    if "MemTotal" not in valeurs or "MemAvailable" not in valeurs:
        logger.warning("Mémoire non mesurable : MemTotal ou MemAvailable absent de /proc/meminfo.")
        return None
    return Memoire(totale_octets=valeurs["MemTotal"], disponible_octets=valeurs["MemAvailable"])


def relever_memoire() -> Memoire | None:
    """Mesure la RAM maintenant. `None` si aucune source n'a pu répondre."""
    return _via_psutil() or _via_proc_meminfo()
