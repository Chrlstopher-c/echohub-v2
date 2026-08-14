"""Mesure de la VRAM et vérification de sa libération après déchargement.

Périmètre volontairement étroit : ce module ne *décide* rien (le dimensionnement appartient au
planificateur), il *constate*. Deux constats seulement sont nécessaires aux adaptateurs :

1. la VRAM occupée avant et après un chargement, pour journaliser ce que le plan a réellement coûté ;
2. la VRAM effectivement rendue après un déchargement — vLLM prélloue et ne rend qu'à l'arrêt du
   processus, et sur 16 Go un modèle qui traîne rend le chargement suivant impossible.

NVML est interrogé, pas `nvidia-smi` : le format texte de l'outil n'est pas un contrat, l'API l'est.
Une machine sans NVML (poste sans GPU, exécution de tests) n'est pas une erreur — la mesure est
alors indisponible et signalée comme telle, jamais remplacée par une estimation.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

from loguru import logger
from pydantic import BaseModel

# Marge tolérée sur le retour à la ligne de base après déchargement. Elle couvre le contexte CUDA
# résiduel du processus hôte, pas un dimensionnement de modèle : ne pas s'en servir pour planifier.
#
# MESURÉE, pas raisonnée. La valeur d'origine (256 Mo) était posée au jugé et rendait tout second
# chargement impossible : le contexte CUDA d'un processus ne se libère JAMAIS tant que le processus
# vit — décharger un modèle rend ses poids, pas le contexte du pilote.
#
# Relevés du 2026-08-14, RTX 5080 / CUDA 12.8 / WSL2, après déchargement complet :
#     305 Mo au-dessus de la ligne de base
#     384 Mo au-dessus de la ligne de base
# Le résidu varie avec les kernels que la génération a fait charger, sans s'accumuler d'un cycle à
# l'autre : ce n'est pas une fuite, et élargir la marge ne masque donc rien. 768 Mo passe au-dessus
# du plus haut relevé sans rendre le contrôle inutile — une VRAM réellement non rendue se compte en
# gigaoctets, pas en centaines de mégaoctets.
MARGE_LIBERATION_OCTETS = 768 * 1024 * 1024

# Bornes du sondage de libération. vLLM rend sa VRAM à la mort du processus : au-delà de cette
# fenêtre, ce n'est plus de la latence, c'est un processus qui ne meurt pas.
TENTATIVES_LIBERATION_MAX = 30
INTERVALLE_LIBERATION_S = 0.5


class MesureVram(BaseModel):
    """Instantané de l'occupation d'un GPU, en octets."""

    index: int
    total_octets: int
    utilisee_octets: int
    libre_octets: int

    @property
    def libre_mo(self) -> int:
        return self.libre_octets // (1024 * 1024)

    @property
    def utilisee_mo(self) -> int:
        return self.utilisee_octets // (1024 * 1024)


class ResultatLiberation(BaseModel):
    """Verdict de la vérification de libération : constaté, pas supposé."""

    verifiee: bool
    mesurable: bool
    tentatives: int
    mesure_finale: MesureVram | None = None
    message: str = ""


@lru_cache(maxsize=1)
def _nvml() -> Any | None:
    """Initialise NVML une seule fois. Retourne None si la bibliothèque ou le pilote manquent."""
    try:
        import pynvml

        pynvml.nvmlInit()
        logger.debug("NVML initialisé : mesure VRAM disponible")
        return pynvml
    except Exception as exc:  # pynvml lève NVMLError, ImportError ou OSError selon la panne
        logger.warning("NVML indisponible, la VRAM ne sera pas mesurée : {}", exc)
        return None


def lire_vram(index: int = 0) -> MesureVram | None:
    """Occupation courante du GPU `index`, ou None si la mesure est impossible sur cette machine."""
    pynvml = _nvml()
    if pynvml is None:
        return None
    try:
        poignee = pynvml.nvmlDeviceGetHandleByIndex(index)
        info = pynvml.nvmlDeviceGetMemoryInfo(poignee)
        return MesureVram(
            index=index,
            total_octets=int(info.total),
            utilisee_octets=int(info.used),
            libre_octets=int(info.free),
        )
    except Exception as exc:
        logger.warning("Lecture VRAM du GPU {} impossible : {}", index, exc)
        return None


async def attendre_liberation(
    reference: MesureVram | None,
    *,
    index: int = 0,
    marge_octets: int = MARGE_LIBERATION_OCTETS,
    tentatives_max: int = TENTATIVES_LIBERATION_MAX,
    intervalle_s: float = INTERVALLE_LIBERATION_S,
) -> ResultatLiberation:
    """Sonde la VRAM jusqu'au retour à `reference` (± marge), dans une fenêtre bornée.

    `reference` est l'instantané pris AVANT le chargement : c'est la seule cible légitime, la VRAM
    au repos n'étant jamais nulle (bureau Windows, autres processus).
    """
    if reference is None or lire_vram(index) is None:
        return ResultatLiberation(
            verifiee=False,
            mesurable=False,
            tentatives=0,
            message="VRAM non mesurable sur cette machine : libération non vérifiée.",
        )

    cible = reference.utilisee_octets + marge_octets
    derniere: MesureVram | None = None
    for tentative in range(1, tentatives_max + 1):
        derniere = lire_vram(index)
        if derniere is None:
            break
        if derniere.utilisee_octets <= cible:
            logger.info("VRAM libérée après {} sondage(s) : {} Mo utilisés", tentative, derniere.utilisee_mo)
            return ResultatLiberation(verifiee=True, mesurable=True, tentatives=tentative, mesure_finale=derniere)
        await asyncio.sleep(intervalle_s)

    return _echec_liberation(reference, derniere, tentatives_max)


def _echec_liberation(
    reference: MesureVram,
    derniere: MesureVram | None,
    tentatives: int,
) -> ResultatLiberation:
    """Formule le constat d'une VRAM non rendue, chiffré : c'est ce chiffre qui oriente la suite."""
    reste_mo = (derniere.utilisee_octets - reference.utilisee_octets) // (1024 * 1024) if derniere else 0
    message = (
        f"VRAM non rendue après {tentatives} sondages : {reste_mo} Mo au-dessus de la ligne de base. "
        "Un processus moteur survit probablement au déchargement."
    )
    logger.error(message)
    return ResultatLiberation(
        verifiee=False, mesurable=True, tentatives=tentatives, mesure_finale=derniere, message=message,
    )
