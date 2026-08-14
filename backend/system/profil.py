"""Agrégation du profil machine — la source de vérité matérielle du planificateur.

Chaque appel produit un instantané neuf : plateforme, contraintes, GPU, VRAM libre, RAM
disponible, pilote. Rien n'est mémorisé. La VRAM libre change entre deux chargements, et c'est
exactement la valeur sur laquelle le planificateur décide combien de couches partent sur le GPU.

Les avertissements produits ici sont destinés à être affichés : ils disent ce qui manque et ce que
cela coûte, pour que l'utilisateur comprenne un plan dégradé au lieu de le subir.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from backend.system.gpu import relever_gpu
from backend.system.memoire import relever_memoire
from backend.system.modeles import (
    VERSION_PILOTE_MIN_BLACKWELL,
    ContraintesPlateforme,
    Memoire,
    ProfilMachine,
    ReleveGpu,
    SourceMesureGpu,
)
from backend.system.plateforme import contraintes_plateforme, detecter_plateforme


def _avertissements_gpu(releve: ReleveGpu) -> list[str]:
    """Ce qui manque côté GPU et ce que cela implique pour le plan de chargement."""
    messages: list[str] = []
    if not releve.gpus:
        messages.append(
            "Aucun GPU NVIDIA détecté : inférence CPU uniquement, débit sans commune mesure "
            "avec un chargement GPU."
        )
        return messages

    if releve.source is SourceMesureGpu.NVIDIA_SMI:
        messages.append(
            "NVML indisponible : les mesures viennent du texte de nvidia-smi, dont le format "
            "n'est pas un contrat. Certaines valeurs peuvent manquer."
        )
    if releve.pilote is None:
        messages.append("Version du pilote NVIDIA illisible : le seuil Blackwell n'a pas pu être vérifié.")
    elif any(gpu.est_blackwell for gpu in releve.gpus) and not releve.pilote.supporte_blackwell:
        messages.append(
            f"Pilote NVIDIA {releve.pilote.version} sous le plancher {VERSION_PILOTE_MIN_BLACKWELL} "
            "requis par les RTX 50xx : chargement GPU instable ou impossible."
        )
    return messages


def _avertissements_memoire(memoire: Memoire | None, contraintes: ContraintesPlateforme) -> list[str]:
    """Ce qui manque côté RAM, et le plafond WSL2 qui limite silencieusement l'offload CPU."""
    messages: list[str] = []
    if memoire is None:
        messages.append("RAM non mesurable : aucun offload CPU ne doit être planifié à l'aveugle.")
    elif contraintes.ram_plafonnee_par_hote:
        gio = memoire.totale_octets / 1024**3
        messages.append(
            f"RAM vue par WSL2 : {gio:.1f} Gio, plafonnée par défaut à environ 50 % de l'hôte. "
            "Un `.wslconfig` explicite est nécessaire pour élargir la marge d'offload CPU."
        )
    return messages


def profil_machine() -> ProfilMachine:
    """Mesure complète de la machine, maintenant.

    À rappeler avant chaque planification : un profil conservé d'un chargement à l'autre décrit
    une machine qui n'existe plus.
    """
    plateforme, version_noyau = detecter_plateforme()
    contraintes = contraintes_plateforme(plateforme)
    releve = relever_gpu()
    memoire = relever_memoire()

    profil = ProfilMachine(
        mesure_le=datetime.now(timezone.utc),
        plateforme=plateforme,
        version_noyau=version_noyau,
        contraintes=contraintes,
        source_gpu=releve.source,
        pilote=releve.pilote,
        gpus=releve.gpus,
        memoire=memoire,
        avertissements=_avertissements_gpu(releve) + _avertissements_memoire(memoire, contraintes),
    )
    _journaliser(profil)
    return profil


def _journaliser(profil: ProfilMachine) -> None:
    """Trace le profil retenu : sans elle, un plan dégradé reste inexplicable après coup."""
    principal = profil.gpu_principal
    description = "aucun GPU"
    if principal is not None:
        libre_gio = principal.vram_libre_octets / 1024**3
        totale_gio = principal.vram_totale_octets / 1024**3
        description = (
            f"{principal.nom} ({principal.architecture_sm or 'sm inconnu'}), "
            f"VRAM {libre_gio:.1f}/{totale_gio:.1f} Gio libres"
        )
    logger.info(
        "Profil machine : {} | {} | source {} | RAM disponible {:.1f} Gio",
        profil.plateforme.value,
        description,
        profil.source_gpu.value,
        profil.ram_disponible_octets / 1024**3,
    )
    for avertissement in profil.avertissements:
        logger.warning("Profil machine : {}", avertissement)
