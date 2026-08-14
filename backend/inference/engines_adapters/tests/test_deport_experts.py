"""Tests du déport des experts en mémoire hôte — la partie où une erreur ne lèverait rien.

Ce sous-module écrit dans une struct C par décalage et fabrique des expressions régulières lues par
llama.cpp. Les deux échouent en silence : un décalage faux écrit un pointeur dans un autre champ, un
motif trop large déporte des tenseurs qu'on voulait garder en VRAM, et `Llama.__init__` avale sans
broncher tout argument inconnu. D'où des tests sur les invariants qu'aucune exception ne signalerait.

Aucun moteur n'est chargé ici : tout ce qui est vérifié est pur.
"""

from __future__ import annotations

import ctypes
import logging
import re

from backend.inference.engines_adapters.contrat import CauseEchec, MoteurSupporte, PlanChargement
from backend.inference.engines_adapters.experts_hote import (
    DECALAGE_OVERRIDES_ATTENDU,
    TAILLE_MODEL_PARAMS_ATTENDUE,
    CollecteurJournal,
    Surcharges,
    SurchargeBufferTenseur,
    motif_experts,
    verifier_application,
    verifier_support,
)
from backend.inference.engines_adapters.traduction_plan import vers_cause_planificateur

# Noms de tenseurs tels que llama.cpp les présente au filtre de surcharge.
TENSEUR_EXPERTS_BLOC_1 = "blk.1.ffn_gate_exps.weight"
TENSEUR_EXPERTS_BLOC_11 = "blk.11.ffn_gate_exps.weight"
TENSEUR_DENSE_BLOC_1 = "blk.1.ffn_down.weight"


def _capture(*messages: str) -> CollecteurJournal:
    """Collecteur alimenté par des lignes de journal, sans passer par le moteur."""
    collecteur = CollecteurJournal()
    for message in messages:
        collecteur.emit(logging.LogRecord("test", logging.INFO, "", 0, message, None, None))
    return collecteur


def test_motif_dun_bloc_ne_capture_pas_le_bloc_voisin() -> None:
    """Sans point échappé, `blk.1.` attraperait `blk.11.` et déporterait un bloc non prévu."""
    motif = motif_experts(1)
    assert re.search(motif, TENSEUR_EXPERTS_BLOC_1) is not None
    assert re.search(motif, TENSEUR_EXPERTS_BLOC_11) is None
    assert re.search(motif, "blk.10.ffn_gate_exps.weight") is None


def test_motif_ne_capture_que_les_tenseurs_dexperts() -> None:
    """Déporter le dense d'un bloc annulerait tout le gain : il est lu à chaque token."""
    assert re.search(motif_experts(1), TENSEUR_DENSE_BLOC_1) is None
    for nom in ("ffn_gate_exps", "ffn_up_exps", "ffn_down_exps"):
        assert re.search(motif_experts(1), f"blk.1.{nom}.weight") is not None


def test_struct_de_surcharge_nest_pas_celle_de_quantification() -> None:
    """Celle du binding est `{c_char_p, c_int}` : la réutiliser décalerait le tableau de 4 octets."""
    champs = {nom: getattr(SurchargeBufferTenseur, nom).offset for nom, _ in SurchargeBufferTenseur._fields_}
    assert champs == {"pattern": 0, "buft": 8}
    assert ctypes.sizeof(SurchargeBufferTenseur) == 16


def test_tableau_de_surcharges_se_termine_par_une_entree_nulle() -> None:
    """C'est l'entrée à `pattern` NULL qui borne le parcours côté C : sans elle, il lit au-delà."""
    surcharges = Surcharges((3, 7), 0xDEADBEEF)

    assert len(surcharges.tableau) == 3
    assert surcharges.tableau[0].buft == 0xDEADBEEF
    assert surcharges.tableau[2].pattern is None
    # Les motifs encodés doivent rester référencés : le C ne garde que leurs adresses.
    assert len(surcharges.motifs) == 2


def test_support_refuse_un_binding_dont_la_disposition_a_change() -> None:
    """Garde ABI : une struct réordonnée ferait écrire un pointeur dans le mauvais champ, sans erreur."""

    class _ParametresDecales(ctypes.Structure):
        _fields_ = [("autre_chose", ctypes.c_void_p), ("tensor_buft_overrides", ctypes.c_void_p)]

    class _ModuleFactice:
        llama_model_params = _ParametresDecales

    support = verifier_support(_ModuleFactice())

    assert support.disponible is False
    assert "Disposition" in support.raison
    assert str(TAILLE_MODEL_PARAMS_ATTENDUE) in support.raison
    assert str(DECALAGE_OVERRIDES_ATTENDU) in support.raison


def test_support_refuse_un_binding_sans_struct_de_parametres() -> None:
    """Aucune supposition sur ce qui n'est pas là : le refus est nommé, pas une exception nue."""

    class _ModuleVide:
        pass

    support = verifier_support(_ModuleVide())

    assert support.disponible is False
    assert support.buffer_type_hote is None


def test_deport_non_constate_dans_le_journal_est_un_echec() -> None:
    """Un bloc demandé mais absent du journal a gardé ses experts en VRAM : le plan est trahi."""
    collecteur = _capture(f"tensor {TENSEUR_EXPERTS_BLOC_1} buffer type overridden to CUDA_Host")

    applique, message = verifier_application(collecteur, (1, 9))

    assert applique is False
    assert "9" in message


def test_journal_muet_vaut_deport_non_applique() -> None:
    """L'absence de preuve n'est pas une preuve : `Llama` construit sans erreur un objet qui n'a rien fait."""
    applique, message = verifier_application(_capture(), (1,))

    assert applique is False
    assert "aucune ligne" in message


def test_deport_confirme_pour_chaque_bloc_demande() -> None:
    """Une ligne par bloc suffit : exiger trois tenseurs par bloc inventerait une contrainte de fichier."""
    collecteur = _capture(
        f"tensor {TENSEUR_EXPERTS_BLOC_1} buffer type overridden to CUDA_Host",
        "tensor blk.9.ffn_up_exps.weight buffer type overridden to CUDA_Host",
        "CUDA0 compute buffer size = 298.50 MiB",
    )

    applique, _ = verifier_application(collecteur, (1, 9))

    assert applique is True
    # Le journal est aussi un canal de mesure : les tailles de tampons y sont lues, pas estimées.
    assert collecteur.lignes_tampons == ["CUDA0 compute buffer size = 298.50 MiB"]


def test_plan_moteur_transporte_les_blocs_dexperts_deportes() -> None:
    """Le contrat des adaptateurs doit porter le second axe de placement, sinon il se perd en route."""
    plan = PlanChargement(
        moteur=MoteurSupporte.LLAMA_CPP,
        chemin_modele="/modeles/moe.gguf",
        couches_gpu=40,
        experts_deportes=[1, 2, 3, 4],
        contexte=32768,
        batch=2048,
    )

    assert plan.experts_deportes == [1, 2, 3, 4]
    assert plan.couches_gpu == 40, "sur un MoE déporté, ce champ ne décrit plus seul le placement"


def test_cause_de_deport_indisponible_disqualifie_la_strategie() -> None:
    """Elle ne doit pas se traduire en manque de VRAM : le levier de dégradation n'est pas le même."""
    cause = vers_cause_planificateur(CauseEchec.DEPORT_EXPERTS_INDISPONIBLE)

    assert cause.value == "deport_experts_indisponible"
