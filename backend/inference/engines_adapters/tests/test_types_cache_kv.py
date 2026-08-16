"""Verrou sur les types de cache KV : ne jamais proposer ce que le backend ne sait pas servir.

Régression réelle du 2026-08-16, et elle a tué le backend. Le binaire expose trente-trois types
ggml ; en déduire qu'ils sont tous utilisables COMME CACHE était faux. `q2_0` a produit :

    ggml-backend.cpp:898: pre-allocated tensor (cache_k_l11 (view)) in a buffer (CUDA0)
    that cannot run the operation (SET_ROWS)

soit un `ggml_abort()` — SIGABRT natif, qu'aucun `try/except` Python ne rattrape. Qu'un type existe
dit qu'on sait encoder des poids avec ; servir un cache demande en plus que le backend sache écrire
dedans. Les deux listes (adaptateur et planificateur) doivent rester restrictives ET accordées.
"""

from __future__ import annotations

from backend.inference.engines_adapters.adaptateur_llama_cpp import TYPES_KV
from backend.inference.planner.entrees import TypeCacheKV
from backend.inference.planner.plan import OCTETS_PAR_ELEMENT_KV

# Éprouvés par un chargement ET une génération réels, pas par une lecture de `dir(llama_cpp)`.
_EPROUVES = {"f16", "q8_0", "q4_0"}


def test_aucun_type_de_cache_non_eprouve_n_est_propose() -> None:
    proposes = {t.value for t in TypeCacheKV}
    assert proposes == _EPROUVES, (
        f"types non éprouvés exposés au planificateur : {sorted(proposes - _EPROUVES)}. "
        "`q2_0` et `q1_0` tuent le processus au chargement (SET_ROWS absent sur CUDA)."
    )


def test_l_adaptateur_couvre_exactement_ce_que_le_planificateur_propose() -> None:
    """Un type planifiable mais inconnu de l'adaptateur ferait échouer le chargement à l'arrivée."""
    assert _EPROUVES <= set(TYPES_KV), f"manquants côté adaptateur : {sorted(_EPROUVES - set(TYPES_KV))}"
    assert set(TYPES_KV) - _EPROUVES <= {"f32"}, "l'adaptateur n'accepte rien d'exotique en plus"


def test_chaque_type_planifiable_a_son_cout_memoire() -> None:
    """Sans coût chiffré, le planificateur dimensionnerait un cache au hasard."""
    assert {t.value for t in OCTETS_PAR_ELEMENT_KV} == _EPROUVES
