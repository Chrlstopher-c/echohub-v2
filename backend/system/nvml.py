"""Mesure GPU via NVML — source primaire.

NVML est l'interface programmatique du pilote NVIDIA : valeurs typées, pas de sous-processus, pas
de format texte à parser. Le format de sortie de `nvidia-smi` n'est pas un contrat, NVML si — d'où
l'ordre de préférence (le repli texte vit dans `nvidia_smi.py`).

Aucune fonction d'ici ne lève : une machine sans GPU, sans pilote ou sans `nvidia-ml-py` retourne
`None` et laisse l'appelant dégrader. Un module de mesure qui explose rend la machine indétectable
au lieu de la déclarer vide.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from backend.system.modeles import Gpu, PiloteNvidia, ReleveGpu, SourceMesureGpu

# Garde-fou : le nombre de GPU vient du pilote, on ne boucle jamais sans borne sur une valeur externe.
_MAX_GPUS = 16

_nvml: Any
try:
    import pynvml as _module_nvml

    _nvml = _module_nvml
except ImportError:  # nvidia-ml-py absent de l'environnement : repli sur nvidia-smi
    _nvml = None


def _texte(valeur: Any) -> str:
    """NVML retourne `bytes` selon les versions de `nvidia-ml-py` : normaliser avant usage."""
    if isinstance(valeur, bytes):
        return valeur.decode("utf-8", errors="replace")
    return str(valeur)


def _utilisation(handle: Any) -> int | None:
    """Métrique secondaire : son absence ne doit pas invalider le relevé mémoire."""
    try:
        return int(_nvml.nvmlDeviceGetUtilizationRates(handle).gpu)
    except Exception as exc:  # NVMLError n'est pas importable de façon fiable, on borne large
        logger.debug("Utilisation GPU indisponible : {}", exc)
        return None


def _temperature(handle: Any) -> int | None:
    try:
        return int(_nvml.nvmlDeviceGetTemperature(handle, _nvml.NVML_TEMPERATURE_GPU))
    except Exception as exc:
        logger.debug("Température GPU indisponible : {}", exc)
        return None


def _capacite_calcul(handle: Any) -> tuple[int | None, int | None]:
    """Compute capability du GPU — lue, jamais déduite du nom commercial."""
    try:
        majeur, mineur = _nvml.nvmlDeviceGetCudaComputeCapability(handle)
        return int(majeur), int(mineur)
    except Exception as exc:
        logger.warning("Compute capability illisible via NVML : {}", exc)
        return None, None


def _lire_gpu(index: int) -> Gpu | None:
    """Relevé d'un GPU. Un GPU illisible est ignoré, les autres restent exploitables."""
    try:
        handle = _nvml.nvmlDeviceGetHandleByIndex(index)
        memoire = _nvml.nvmlDeviceGetMemoryInfo(handle)
        majeur, mineur = _capacite_calcul(handle)
        return Gpu(
            index=index,
            nom=_texte(_nvml.nvmlDeviceGetName(handle)),
            compute_majeur=majeur,
            compute_mineur=mineur,
            vram_totale_octets=int(memoire.total),
            vram_libre_octets=int(memoire.free),
            vram_utilisee_octets=int(memoire.used),
            utilisation_pct=_utilisation(handle),
            temperature_c=_temperature(handle),
        )
    except Exception as exc:
        logger.warning("GPU {} illisible via NVML : {}", index, exc)
        return None


def _lire_gpus() -> list[Gpu]:
    nombre = int(_nvml.nvmlDeviceGetCount())
    if nombre > _MAX_GPUS:
        logger.warning("{} GPU rapportés, lecture limitée aux {} premiers.", nombre, _MAX_GPUS)
    releves = (_lire_gpu(index) for index in range(min(nombre, _MAX_GPUS)))
    return [gpu for gpu in releves if gpu is not None]


def _lire_pilote() -> PiloteNvidia | None:
    try:
        return PiloteNvidia(version=_texte(_nvml.nvmlSystemGetDriverVersion()))
    except Exception as exc:
        logger.warning("Version de pilote NVIDIA illisible via NVML : {}", exc)
        return None


def _fermer() -> None:
    try:
        _nvml.nvmlShutdown()
    except Exception as exc:
        logger.debug("Fermeture NVML échouée : {}", exc)


def lire_via_nvml() -> ReleveGpu | None:
    """Relevé GPU complet via NVML, ou `None` si NVML est absent ou refuse de s'initialiser.

    NVML est initialisé et refermé à chaque appel : la session ne survit pas à la mesure, donc
    aucune valeur ne peut être servie depuis un état gardé en mémoire.
    """
    if _nvml is None:
        logger.debug("NVML indisponible : le paquet nvidia-ml-py n'est pas installé.")
        return None

    try:
        _nvml.nvmlInit()
    except Exception as exc:
        logger.debug("Initialisation NVML impossible (pilote absent ou GPU non exposé) : {}", exc)
        return None

    try:
        return ReleveGpu(source=SourceMesureGpu.NVML, pilote=_lire_pilote(), gpus=_lire_gpus())
    except Exception as exc:
        logger.warning("Lecture NVML interrompue : {}", exc)
        return None
    finally:
        _fermer()
