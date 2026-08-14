"""Échelle de dégradation : les seuls réglages qu'un échec autorise à changer, et dans quel sens.

La v1 réagissait à un échec en **augmentant** les paramètres : contexte 55k puis 131k,
`gpu_memory_utilization` 0.72 puis 0.78 puis 0.80. Elle escaladait vers le mur.

Ici la dégradation n'est pas une décision prise au cas par cas : c'est un parcours d'une échelle
monotone, définie une fois. Chaque palier est plus conservateur que le précédent sur tous ses axes —
la propriété est vérifiée par `echelle_monotone()` et par les tests. Le dernier palier est le mode
minimal : aucune couche sur GPU, contexte plancher, cache le plus compressé.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.inference.planner.entrees import CauseEchec, TypeCacheKV
from backend.inference.planner.plan import OCTETS_PAR_ELEMENT_KV


class Palier(BaseModel):
    """Contraintes appliquées par-dessus les préférences utilisateur, à un niveau de dégradation.

    Les facteurs multiplient la valeur souhaitée : ils ne peuvent que la réduire (tous ≤ 1.0). Le
    type de cache KV, lui, est imposé — c'est le levier le moins coûteux en qualité.
    """

    model_config = ConfigDict(frozen=True)

    niveau: int = Field(ge=0)
    facteur_contexte: float = Field(gt=0.0, le=1.0)
    facteur_batch: float = Field(gt=0.0, le=1.0)
    facteur_couches: float = Field(ge=0.0, le=1.0)
    type_kv_impose: TypeCacheKV | None = None
    resume: str


PALIERS: tuple[Palier, ...] = (
    Palier(
        niveau=0,
        facteur_contexte=1.0,
        facteur_batch=1.0,
        facteur_couches=1.0,
        type_kv_impose=None,
        resume="Plan nominal : préférences utilisateur, plafonnées par ce que la machine permet.",
    ),
    Palier(
        niveau=1,
        facteur_contexte=1.0,
        facteur_batch=1.0,
        facteur_couches=1.0,
        type_kv_impose=TypeCacheKV.Q8_0,
        resume="Cache KV compressé en q8_0 : environ moitié moins de VRAM par token, qualité quasi intacte.",
    ),
    Palier(
        niveau=2,
        facteur_contexte=0.5,
        facteur_batch=1.0,
        facteur_couches=1.0,
        type_kv_impose=TypeCacheKV.Q8_0,
        resume="Contexte divisé par deux : le poste qui grandit le plus vite est le premier réduit.",
    ),
    Palier(
        niveau=3,
        facteur_contexte=0.5,
        facteur_batch=0.5,
        facteur_couches=0.75,
        type_kv_impose=TypeCacheKV.Q8_0,
        resume="Un quart des couches renvoyé sur CPU et batch divisé par deux : débit réduit, charge sûre.",
    ),
    Palier(
        niveau=4,
        facteur_contexte=0.25,
        facteur_batch=0.25,
        facteur_couches=0.5,
        type_kv_impose=TypeCacheKV.Q4_0,
        resume="Moitié des couches sur CPU, contexte au quart, cache q4_0 : dernier palier avec accélération GPU.",
    ),
    Palier(
        niveau=5,
        facteur_contexte=0.05,
        facteur_batch=0.05,
        facteur_couches=0.0,
        type_kv_impose=TypeCacheKV.Q4_0,
        resume="Mode minimal garanti : exécution entièrement CPU, contexte plancher, cache q4_0.",
    ),
)

NIVEAU_MINIMAL = PALIERS[-1].niveau

# Un échec ne redescend pas toujours d'un seul cran : la cause dit quel levier est déjà insuffisant.
# Une saturation VRAM appelle au moins la compression du cache ; une saturation RAM hôte appelle une
# réduction du contexte, puisque c'est le cache KV des couches CPU qui déborde.
NIVEAU_MINIMUM_PAR_CAUSE: dict[CauseEchec, int] = {
    CauseEchec.MEMOIRE_GPU_INSUFFISANTE: 1,
    CauseEchec.MEMOIRE_HOTE_INSUFFISANTE: 2,
    CauseEchec.CONTEXTE_REFUSE: 2,
    CauseEchec.MOTEUR_INDISPONIBLE: 1,
    CauseEchec.INCONNUE: 1,
}


def palier(niveau: int) -> Palier:
    """Palier correspondant au niveau demandé, borné à l'échelle existante."""
    return PALIERS[max(0, min(niveau, NIVEAU_MINIMAL))]


def niveau_minimum_pour_cause(cause: CauseEchec) -> int:
    """Palier le plus haut à partir duquel une nouvelle tentative a un sens, vu la cause de l'échec."""
    return NIVEAU_MINIMUM_PAR_CAUSE.get(cause, 1)


def echelle_monotone() -> bool:
    """Vrai si chaque palier est ≤ au précédent sur tous ses axes. Invariant vérifié par les tests."""
    for precedent, suivant in zip(PALIERS, PALIERS[1:]):
        axes = (
            (suivant.facteur_contexte, precedent.facteur_contexte),
            (suivant.facteur_batch, precedent.facteur_batch),
            (suivant.facteur_couches, precedent.facteur_couches),
            (_cout_kv(suivant), _cout_kv(precedent)),
        )
        if any(apres > avant for apres, avant in axes):
            return False
    return True


def _cout_kv(palier_teste: Palier) -> float:
    """Coût par élément du cache imposé ; le palier sans contrainte vaut le format le plus coûteux."""
    if palier_teste.type_kv_impose is None:
        return OCTETS_PAR_ELEMENT_KV[TypeCacheKV.F16]
    return OCTETS_PAR_ELEMENT_KV[palier_teste.type_kv_impose]
