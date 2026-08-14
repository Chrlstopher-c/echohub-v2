"""Détection de la plateforme et des contraintes qu'elle impose.

WSL2 et Linux natif se ressemblent (même noyau, même `nvidia-smi`) et se comportent de façon
opposée sur deux points mesurés. Ce module fait donc plus que nommer la plateforme : il produit les
contraintes correspondantes, pour que personne d'autre n'ait à retenir la table des pièges.

Toutes les justifications ci-dessous viennent de mesures consignées dans `COMPATIBILITE-GPU.md`.
Ne rien y changer sans une mesure qui contredit la mesure d'origine.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from loguru import logger

from backend.system.modeles import ContraintesPlateforme, Plateforme, SyntaxeGpuDocker

_CHEMIN_PROC_VERSION = Path("/proc/version")

# Marqueur du noyau WSL : `/proc/version` porte la mention du fournisseur du noyau.
_MARQUEUR_WSL = "microsoft"

# Variables posées uniquement par WSL — filet de sécurité si `/proc/version` est illisible.
_VARIABLES_WSL = ("WSL_DISTRO_NAME", "WSL_INTEROP")

_JUSTIF_UM_WSL = (
    "WSL2 ne supporte pas l'oversubscription de mémoire managée. Mesure du 2026-08-14 avec "
    "GGML_CUDA_ENABLE_UNIFIED_MEMORY=1 : 20 Go retenus en RAM, VRAM figée à 2 Go, plusieurs "
    "minutes de chargement pour un modèle inutilisable. Sans mémoire unifiée : 12 s de "
    "chargement, 14,8 Go réellement en VRAM, 19,6 tok/s."
)
_JUSTIF_UM_LINUX = (
    "Sur Linux natif la mémoire unifiée laisse les poids déborder vers la RAM sans blocage. "
    "Elle reste autorisée, pas imposée : c'est au planificateur d'en décider."
)
_JUSTIF_UM_INCONNUE = (
    "Comportement de la mémoire unifiée non mesuré sur cette plateforme. Désactivée par défaut : "
    "un échec doit produire un plan plus conservateur, jamais un pari."
)
_JUSTIF_RAM_WSL = (
    "La VM WSL2 est plafonnée par défaut à environ 50 % de la RAM de l'hôte. La RAM mesurée est "
    "celle de la VM, pas celle de la machine : relever le plafond exige un `.wslconfig` explicite."
)
_JUSTIF_PIN_WSL = "vLLM force pin_memory=False sous WSL et le signale au démarrage : normal, non corrigeable."
_JUSTIF_DOCKER_WSL = (
    "Windows + Docker Desktop + WSL2 : seul `deploy.resources.reservations.devices` fonctionne ; "
    "`nvidia.com/gpu=all` échoue en `unresolvable CDI devices`."
)
_JUSTIF_DOCKER_LINUX = (
    "Linux natif avec CDI seul : `devices: [nvidia.com/gpu=all]` fonctionne ; `--gpus all` échoue "
    "en `AMD CDI spec not found`. La syntaxe est inversée par rapport à WSL2."
)


def _lire_proc_version() -> str:
    """Contenu de `/proc/version`, ou chaîne vide s'il est absent (Windows natif, macOS)."""
    try:
        return _CHEMIN_PROC_VERSION.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        logger.debug("/proc/version illisible : {}", exc)
        return ""


def _wsl_signale_par_environnement() -> bool:
    """Repli quand `/proc/version` est illisible : ces variables n'existent que sous WSL."""
    return any(os.environ.get(nom) for nom in _VARIABLES_WSL)


def detecter_plateforme() -> tuple[Plateforme, str]:
    """Retourne la plateforme et la version de noyau qui a servi à la trancher."""
    systeme = platform.system()
    if systeme == "Windows":
        return Plateforme.WINDOWS, platform.version()
    if systeme == "Darwin":
        return Plateforme.MACOS, platform.release()
    if systeme != "Linux":
        logger.warning("Système non reconnu : {}", systeme or "inconnu")
        return Plateforme.INCONNUE, platform.release()

    version_noyau = _lire_proc_version() or platform.release()
    if _MARQUEUR_WSL in version_noyau.lower() or _wsl_signale_par_environnement():
        return Plateforme.WSL2, version_noyau
    return Plateforme.LINUX_NATIF, version_noyau


def _contraintes_wsl2() -> ContraintesPlateforme:
    return ContraintesPlateforme(
        plateforme=Plateforme.WSL2,
        memoire_unifiee_cuda=False,
        # Poser explicitement la variable à 0 plutôt que l'omettre : un environnement hérité
        # peut la porter à 1, et l'omission laisserait alors le piège actif.
        variables_env_imposees={"GGML_CUDA_ENABLE_UNIFIED_MEMORY": "0"},
        ram_plafonnee_par_hote=True,
        pin_memory_disponible=False,
        syntaxe_gpu_docker=SyntaxeGpuDocker.RESERVATIONS,
        justifications={
            "memoire_unifiee_cuda": _JUSTIF_UM_WSL,
            "ram_plafonnee_par_hote": _JUSTIF_RAM_WSL,
            "pin_memory_disponible": _JUSTIF_PIN_WSL,
            "syntaxe_gpu_docker": _JUSTIF_DOCKER_WSL,
        },
    )


def _contraintes_linux_natif() -> ContraintesPlateforme:
    return ContraintesPlateforme(
        plateforme=Plateforme.LINUX_NATIF,
        memoire_unifiee_cuda=True,
        variables_env_imposees={},
        ram_plafonnee_par_hote=False,
        pin_memory_disponible=True,
        syntaxe_gpu_docker=SyntaxeGpuDocker.CDI,
        justifications={
            "memoire_unifiee_cuda": _JUSTIF_UM_LINUX,
            "syntaxe_gpu_docker": _JUSTIF_DOCKER_LINUX,
        },
    )


def _contraintes_non_mesurees(plateforme: Plateforme) -> ContraintesPlateforme:
    """Plateforme sans mesure : on retient partout l'option la plus conservatrice.

    Windows natif tombe ici tant que rien n'y a été mesuré. La syntaxe Docker retenue est celle
    de Docker Desktop, seul chemin GPU disponible côté Windows.
    """
    return ContraintesPlateforme(
        plateforme=plateforme,
        memoire_unifiee_cuda=False,
        variables_env_imposees={"GGML_CUDA_ENABLE_UNIFIED_MEMORY": "0"},
        ram_plafonnee_par_hote=False,
        pin_memory_disponible=False,
        syntaxe_gpu_docker=SyntaxeGpuDocker.RESERVATIONS,
        justifications={"memoire_unifiee_cuda": _JUSTIF_UM_INCONNUE},
    )


def contraintes_plateforme(plateforme: Plateforme) -> ContraintesPlateforme:
    """Contraintes matérielles associées à une plateforme, justifications comprises."""
    if plateforme is Plateforme.WSL2:
        return _contraintes_wsl2()
    if plateforme is Plateforme.LINUX_NATIF:
        return _contraintes_linux_natif()
    return _contraintes_non_mesurees(plateforme)
