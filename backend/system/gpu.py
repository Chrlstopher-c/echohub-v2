"""Point d'entrée GPU du domaine : arbitre entre les sources de mesure disponibles.

NVML d'abord (valeurs typées, contrat stable), `nvidia-smi` ensuite (texte, format non garanti),
relevé vide en dernier recours. Une machine sans GPU n'est pas une panne : elle produit un relevé
vide que le planificateur traduit en exécution CPU.
"""

from __future__ import annotations

from collections.abc import Callable

from loguru import logger

from backend.system.modeles import ReleveGpu, SourceMesureGpu
from backend.system.nvidia_smi import lire_via_nvidia_smi
from backend.system.nvml import lire_via_nvml

# Ordre d'essai figé : de la source la plus fiable à la moins fiable.
_SOURCES: tuple[Callable[[], ReleveGpu | None], ...] = (lire_via_nvml, lire_via_nvidia_smi)


def relever_gpu() -> ReleveGpu:
    """Mesure l'état GPU maintenant : modèle, compute capability, VRAM totale et VRAM libre.

    Rien n'est mémorisé entre deux appels — la VRAM libre change à chaque chargement, une valeur
    servie depuis un cache serait fausse au moment précis où le planificateur en a besoin.
    """
    for lire in _SOURCES:
        releve = lire()
        if releve is not None and releve.gpus:
            logger.debug("Relevé GPU obtenu via {} ({} GPU).", releve.source.value, len(releve.gpus))
            return releve

    logger.info("Aucun GPU NVIDIA détecté : le planificateur devra viser une exécution CPU.")
    return ReleveGpu(source=SourceMesureGpu.AUCUNE)
