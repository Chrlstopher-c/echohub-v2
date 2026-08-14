"""Tests de la dégradation — le verrou contre l'escalade mesurée sur la v1.

Rappel du défaut rejoué ici : après un échec de chargement, la v1 **augmentait** les paramètres
(contexte 55k puis 131k, `gpu_memory_utilization` 0.72 puis 0.78 puis 0.80). Ces tests échouent au
premier plan dégradé qui remonterait un seul axe.
"""

from __future__ import annotations

import pytest

from backend.core import PlanificationImpossible
from backend.inference.planner import (
    NIVEAU_MINIMAL,
    OCTETS_PAR_ELEMENT_KV,
    CauseEchec,
    MetadonneesModele,
    PlanDeChargement,
    PreferencesUtilisateur,
    degrader,
    planifier,
)

from .conftest import demande, profil_5080

# Borne de sécurité de la boucle de dégradation en test : l'échelle est finie, on ne la parcourt
# jamais plus d'une fois.
MAX_DEGRADATIONS = NIVEAU_MINIMAL + 1


def test_degradation_produit_un_plan_strictement_plus_conservateur(modele_grand: MetadonneesModele) -> None:
    """Le premier plan dégradé demande moins sur tous les axes, et au moins un strictement moins."""
    entree = demande(modele_grand, preferences=PreferencesUtilisateur(contexte=57344))
    initial = planifier(entree)

    suivant = degrader(entree, initial, CauseEchec.MEMOIRE_GPU_INSUFFISANTE)

    assert suivant.est_plus_conservateur_que(initial) is True
    assert suivant.niveau_degradation > initial.niveau_degradation


def test_premiere_degradation_reste_graduelle(modele_grand: MetadonneesModele) -> None:
    """Le premier cran ne sacrifie que le format du cache : contexte et couches sont préservés.

    Sans plafond hérité du plan échoué, ce palier proposerait *plus* de couches (le cache compressé
    libère de la VRAM), serait écarté comme non conservateur, et la dégradation sauterait d'un coup
    à un plan bien plus pauvre.
    """
    entree = demande(modele_grand, preferences=PreferencesUtilisateur(contexte=57344))
    initial = planifier(entree)

    suivant = degrader(entree, initial, CauseEchec.MEMOIRE_GPU_INSUFFISANTE)

    assert suivant.niveau_degradation == initial.niveau_degradation + 1
    assert suivant.contexte.valeur == initial.contexte.valeur
    assert suivant.couches_gpu.valeur == initial.couches_gpu.valeur
    assert _cout_kv(suivant) < _cout_kv(initial)
    assert suivant.budget.vram_requise_octets < initial.budget.vram_requise_octets


def test_degradation_ne_remonte_jamais_le_contexte(modele_grand: MetadonneesModele) -> None:
    """Régression v1 : contexte 55k puis 131k après échec. Chaque étape doit rétrécir ou stagner."""
    entree = demande(modele_grand, preferences=PreferencesUtilisateur(contexte=57344))
    plan = planifier(entree)
    precedents = [plan]

    for _ in range(MAX_DEGRADATIONS):
        try:
            plan = degrader(entree, plan, CauseEchec.MEMOIRE_GPU_INSUFFISANTE)
        except PlanificationImpossible:
            break
        dernier = precedents[-1]
        assert plan.contexte.valeur <= dernier.contexte.valeur
        assert plan.couches_gpu.valeur <= dernier.couches_gpu.valeur
        assert plan.batch.valeur <= dernier.batch.valeur
        assert _cout_kv(plan) <= _cout_kv(dernier)
        precedents.append(plan)

    assert len(precedents) > 1, "au moins une dégradation doit être possible depuis le plan nominal"


def test_chaine_de_degradations_atteint_le_mode_minimal(modele_grand: MetadonneesModele) -> None:
    """Le bas de l'échelle est un plan entièrement CPU, garanti tant que la RAM suffit."""
    entree = demande(modele_grand, preferences=PreferencesUtilisateur(contexte=57344))
    plan = planifier(entree)

    for _ in range(MAX_DEGRADATIONS):
        try:
            plan = degrader(entree, plan, CauseEchec.MEMOIRE_GPU_INSUFFISANTE)
        except PlanificationImpossible:
            break

    assert plan.couches_gpu.valeur == 0
    assert plan.niveau_degradation == NIVEAU_MINIMAL
    assert plan.budget.ram_requise_octets <= plan.budget.ram_disponible_octets


def test_echelle_epuisee_leve_planification_impossible(modele_grand: MetadonneesModele) -> None:
    """Dégrader le mode minimal n'a pas de sens : l'erreur est explicite, pas un plan bricolé."""
    entree = demande(modele_grand, preferences=PreferencesUtilisateur(contexte=57344))
    plan = planifier(entree, niveau_minimum=NIVEAU_MINIMAL)

    with pytest.raises(PlanificationImpossible):
        degrader(entree, plan, CauseEchec.MEMOIRE_GPU_INSUFFISANTE)


def test_cause_ram_saute_directement_a_la_reduction_de_contexte(modele_grand: MetadonneesModele) -> None:
    """Compresser le cache GPU ne libère pas de RAM hôte : la cause choisit le bon levier."""
    entree = demande(modele_grand, preferences=PreferencesUtilisateur(contexte=57344))
    initial = planifier(entree)

    suivant = degrader(entree, initial, CauseEchec.MEMOIRE_HOTE_INSUFFISANTE)

    assert suivant.niveau_degradation >= 2
    assert suivant.contexte.valeur < initial.contexte.valeur


def test_ram_trop_juste_fait_descendre_le_planificateur_dun_palier(modele_grand: MetadonneesModele) -> None:
    """Les couches renvoyées sur CPU coûtent de la RAM : un palier qui n'y tient pas est écarté seul.

    À 6 Gio libres, le plan nominal réclame 6,3 Gio de RAM hôte. Le planificateur ne rend pas ce
    plan « en espérant » : il descend d'un cran, où le cache compressé rend une couche au GPU.
    """
    entree = demande(
        modele_grand,
        profil_5080(ram_libre_gio=6.0),
        PreferencesUtilisateur(contexte=32768),
    )
    plan = planifier(entree)

    assert plan.niveau_degradation >= 1
    assert plan.budget.ram_requise_octets <= plan.budget.ram_disponible_octets


def test_ram_notoirement_insuffisante_ne_produit_aucun_plan(modele_grand: MetadonneesModele) -> None:
    """17,5 Gio de poids pour 2 Gio de RAM et 14,7 Gio de VRAM : l'échec est franc, pas un plan bancal."""
    entree = demande(
        modele_grand,
        profil_5080(ram_libre_gio=2.0),
        PreferencesUtilisateur(contexte=32768),
    )
    with pytest.raises(PlanificationImpossible):
        planifier(entree)


def _cout_kv(plan: PlanDeChargement) -> float:
    """Octets par élément du cache KV retenu — plus petit vaut plus compressé."""
    return OCTETS_PAR_ELEMENT_KV[plan.type_cache_kv.valeur]
