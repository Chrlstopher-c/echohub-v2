"""Tests du plan nominal : mesure du poids par couche, marges, plafonnements, plateformes.

Chaque test correspond à un défaut réel de la v1, rejoué sans GPU. Si l'un d'eux repasse au vert
alors qu'il devrait échouer, c'est que le planificateur a recommencé à supposer au lieu de calculer.
"""

from __future__ import annotations

import pytest

from backend.core import PlanificationImpossible
from backend.inference.planner import (
    NOM_MEMOIRE_UNIFIEE,
    MetadonneesModele,
    ModeleCharge,
    Moteur,
    PlanDeChargement,
    Plateforme,
    PreferencesUtilisateur,
    TypeCacheKV,
    planifier,
    poids_par_couche_octets,
)
from backend.inference.planner.paliers import echelle_monotone

from .conftest import GIO, MIO, POIDS_COUCHE_MESURE_MIO, demande, profil_5080


def test_poids_par_couche_est_mesure_pas_suppose(modele_grand: MetadonneesModele) -> None:
    """Régression v1 : 150 Mo/couche supposés là où le fichier en donne 436."""
    poids_mio = poids_par_couche_octets(modele_grand) / MIO
    assert poids_mio == pytest.approx(POIDS_COUCHE_MESURE_MIO, rel=1e-6)
    assert poids_mio > 400, "le poids par couche doit venir de la taille du fichier, pas d'un palier"


def test_modele_plus_gros_que_la_vram_repartit_sans_saturer(modele_grand: MetadonneesModele) -> None:
    """Le modèle pèse 17,5 Gio pour 14,7 Gio libres : partage GPU/CPU, jamais de dépassement."""
    plan = planifier(demande(modele_grand, preferences=PreferencesUtilisateur(contexte=57344)))

    assert 0 < plan.couches_gpu.valeur < plan.couches_totales
    assert plan.couches_gpu.valeur <= 41, "régression v1 : 64 couches déduites pour un modèle qui en a 41"
    assert plan.couches_gpu.plafonnee is True
    assert plan.budget.vram_requise_octets <= plan.budget.vram_disponible_octets
    assert plan.couches_cpu > 0


def test_marge_couvre_kv_tampons_et_fragmentation(modele_grand: MetadonneesModele) -> None:
    """La marge n'est pas un forfait : elle se décompose et grandit avec le contexte demandé."""
    court = planifier(demande(modele_grand, preferences=PreferencesUtilisateur(contexte=8192)))
    long = planifier(demande(modele_grand, preferences=PreferencesUtilisateur(contexte=57344)))

    libelles = [poste.libelle for poste in long.budget.postes]
    assert "Cache KV" in libelles and "Tampons de calcul" in libelles
    assert "Réserve de fragmentation" in libelles

    kv_par_couche_court = _poste(court, "Cache KV") / max(court.couches_gpu.valeur, 1)
    kv_par_couche_long = _poste(long, "Cache KV") / max(long.couches_gpu.valeur, 1)
    assert kv_par_couche_long > kv_par_couche_court
    assert long.couches_gpu.valeur < court.couches_gpu.valeur


def test_modele_qui_tient_largement_va_entierement_sur_gpu(modele_petit: MetadonneesModele) -> None:
    """Rien ne doit être raboté quand tout tient : pas de prudence décorative."""
    plan = planifier(demande(modele_petit, preferences=PreferencesUtilisateur(contexte=8192)))

    assert plan.couches_gpu.valeur == plan.couches_totales
    assert plan.couches_gpu.plafonnee is False
    assert plan.contexte.valeur == 8192
    assert plan.contexte.plafonnee is False
    assert plan.type_cache_kv.valeur is TypeCacheKV.F16
    assert plan.niveau_degradation == 0


def test_contexte_demande_au_dela_de_lentrainement_est_plafonne(modele_petit: MetadonneesModele) -> None:
    """Un contexte au-delà de l'entraînement est ramené, et le plan le dit."""
    plan = planifier(demande(modele_petit, preferences=PreferencesUtilisateur(contexte=131072)))

    assert plan.contexte.valeur == modele_petit.contexte_entrainement_max
    assert plan.contexte.plafonnee is True
    assert plan.contexte.valeur_demandee == 131072
    assert "entraînement" in plan.contexte.justification


def test_couches_demandees_au_dela_du_possible_sont_plafonnees(modele_grand: MetadonneesModele) -> None:
    """Régression v1 directe : 64 couches demandées pour un modèle qui en compte 41."""
    plan = planifier(demande(modele_grand, preferences=PreferencesUtilisateur(contexte=32768, couches_gpu=64)))

    assert plan.couches_gpu.valeur < 64
    assert plan.couches_gpu.valeur <= modele_grand.nombre_couches
    assert plan.couches_gpu.plafonnee is True


def test_preference_plus_conservatrice_est_respectee(modele_petit: MetadonneesModele) -> None:
    """Demander moins que le possible est un droit : le plan ne le « corrige » pas."""
    plan = planifier(demande(modele_petit, preferences=PreferencesUtilisateur(contexte=4096, couches_gpu=10)))

    assert plan.couches_gpu.valeur == 10
    assert plan.couches_gpu.plafonnee is False
    assert plan.contexte.valeur == 4096


def test_wsl2_refuse_la_memoire_unifiee_meme_demandee(modele_grand: MetadonneesModele) -> None:
    """Mesure du 2026-08-14 : sous WSL2 la mémoire unifiée fige la VRAM à 2 Go. Refus inconditionnel."""
    preferences = PreferencesUtilisateur(contexte=32768, autoriser_memoire_unifiee=True)
    plan = planifier(demande(modele_grand, profil_5080(Plateforme.WSL2), preferences))

    assert NOM_MEMOIRE_UNIFIEE not in plan.environnement
    refusees = {variable.nom: variable.raison for variable in plan.variables_refusees}
    assert NOM_MEMOIRE_UNIFIEE in refusees
    assert "WSL2" in refusees[NOM_MEMOIRE_UNIFIEE]


def test_linux_natif_pose_la_memoire_unifiee_si_elle_est_demandee(modele_grand: MetadonneesModele) -> None:
    """Même modèle, même machine, plateforme différente : le plan diffère sur ce seul point."""
    preferences = PreferencesUtilisateur(contexte=32768, autoriser_memoire_unifiee=True)
    natif = planifier(demande(modele_grand, profil_5080(Plateforme.LINUX_NATIF), preferences))
    wsl = planifier(demande(modele_grand, profil_5080(Plateforme.WSL2), preferences))

    assert natif.couches_cpu > 0, "le cas n'a de sens que si des couches débordent sur le CPU"
    assert natif.environnement.get(NOM_MEMOIRE_UNIFIEE) == "1"
    assert NOM_MEMOIRE_UNIFIEE not in wsl.environnement
    assert natif.couches_gpu.valeur == wsl.couches_gpu.valeur, "seul l'environnement doit changer"


def test_gpu_exclusif_exige_lejection_des_modeles_charges(modele_grand: MetadonneesModele) -> None:
    """vLLM ne rend sa VRAM qu'à l'arrêt : tout modèle résident doit être éjecté, et compté comme rendu."""
    charge = ModeleCharge(identifiant="autre-modele", moteur=Moteur.VLLM, vram_octets=10 * GIO)
    profil = profil_5080(vram_libre_gio=4.0, charges=(charge,))
    plan = planifier(demande(modele_grand, profil, PreferencesUtilisateur(contexte=32768)))

    assert [ejection.identifiant for ejection in plan.ejections_requises] == ["autre-modele"]
    assert plan.budget.vram_disponible_octets > 4 * GIO


def test_vllm_sans_repartition_possible_degrade_puis_echoue(modele_safetensors: MetadonneesModele) -> None:
    """vLLM charge tout ou rien : un modèle de 17,5 Gio sur 14,7 Gio libres n'a aucun plan."""
    profil = profil_5080(moteurs=(Moteur.VLLM,))
    with pytest.raises(PlanificationImpossible):
        planifier(demande(modele_safetensors, profil))


def test_echelle_de_paliers_est_monotone() -> None:
    """Invariant structurel : aucun palier n'est plus généreux que le précédent, sur aucun axe."""
    assert echelle_monotone() is True


def _poste(plan: PlanDeChargement, libelle: str) -> int:
    """Octets d'un poste du budget, par son libellé."""
    return next(poste.octets for poste in plan.budget.postes if poste.libelle == libelle)
