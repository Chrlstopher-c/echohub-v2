"""Tests du poids mesuré des experts, bloc par bloc — la grandeur qui rend un déport décidable.

Pourquoi cette mesure existe : sur le fichier réel, un bloc pèse 353 Mo dont 335 Mo d'experts routés,
lus à 8 sur 256 par token, et 19,5 Mo de dense lus intégralement à CHAQUE token. Sortir un bloc
entier de la VRAM coûte donc trois fois le trafic hôte que coûte en sortir les seuls experts. Sans la
distinction, le planificateur n'a que le total du bloc et ne peut arbitrer qu'au mauvais grain.

Les chiffres attendus ici se recalculent à la main depuis les formes déclarées dans `fabrique_gguf` :
aucun n'est le résultat d'un facteur.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models.gguf_metadata import MesuresTenseurs, depuis_entete
from backend.models.gguf_reader import InfoTenseur
from backend.models.gguf_types import est_tenseur_expert, porte_attention

from .fabrique_gguf import (
    BLOCS_ATTENTION,
    NB_BLOCS,
    OCTETS_ATTENTION_PAR_BLOC,
    OCTETS_DENSE_PAR_BLOC,
    OCTETS_EXPERTS_PAR_BLOC,
    OCTETS_HORS_BLOCS,
    cles_denses,
    cles_moe,
    entete_en_memoire,
    tenseurs_denses,
    tenseurs_moe,
)


def _mesures_moe() -> MesuresTenseurs:
    """Mesures du MoE de référence. `depuis_entete` garantit qu'elles existent : 733 descripteurs lus."""
    mesures = depuis_entete(entete_en_memoire(cles_moe(), tenseurs_moe())).mesures
    assert mesures is not None, "des descripteurs sont présents, la mesure doit exister"
    return mesures


# --------------------------------------------------------------- reconnaissance des noms de tenseurs


@pytest.mark.parametrize(
    "nom",
    ["blk.0.ffn_gate_exps.weight", "blk.12.ffn_up_exps.weight", "blk.39.ffn_down_exps.weight"],
)
def test_tenseurs_dexperts_routes_reconnus(nom: str) -> None:
    """Les trois portes du FFN d'un MoE, telles que llama.cpp les nomme."""
    assert est_tenseur_expert(nom) is True


def test_expert_partage_nest_pas_un_expert_route() -> None:
    """L'invariant qui protège 0,7 Gio de dense : `_shexp` est actif à chaque token, jamais déporté."""
    assert est_tenseur_expert("blk.0.ffn_gate_shexp.weight") is False
    assert est_tenseur_expert("blk.0.ffn_up_shexp.weight") is False


@pytest.mark.parametrize(
    "nom",
    ["blk.0.ffn_norm.weight", "blk.0.attn_q.weight", "token_embd.weight", "output.weight"],
)
def test_tenseurs_denses_ne_passent_pas_pour_des_experts(nom: str) -> None:
    """Tout le reste du bloc est dense : l'attention, les normes, les tenseurs hors blocs."""
    assert est_tenseur_expert(nom) is False


def test_projection_de_requetes_reconnue() -> None:
    """C'est elle qui dit qu'un bloc porte une attention, donc un cache KV."""
    assert porte_attention("blk.3.attn_q.weight") is True
    assert porte_attention("blk.3.attn_qkv.weight") is True
    assert porte_attention("blk.3.ffn_norm.weight") is False


# ------------------------------------------------------------------------- poids mesuré par bloc


def test_poids_des_experts_par_bloc() -> None:
    """Trois tenseurs d'experts par bloc, 16 384 octets chacun : 49 152 par bloc, sur les quatre."""
    mesures = _mesures_moe()

    assert mesures.octets_experts_par_bloc == [OCTETS_EXPERTS_PAR_BLOC] * NB_BLOCS
    assert mesures.octets_experts_totaux == NB_BLOCS * OCTETS_EXPERTS_PAR_BLOC


def test_poids_dense_est_le_complement_du_bloc() -> None:
    """Ce qui reste après les experts : expert partagé, norme, et l'attention là où elle existe."""
    mesures = _mesures_moe()

    attendus = [
        OCTETS_DENSE_PAR_BLOC + (OCTETS_ATTENTION_PAR_BLOC if bloc in BLOCS_ATTENTION else 0)
        for bloc in range(NB_BLOCS)
    ]
    assert mesures.octets_denses_par_bloc == attendus
    assert mesures.octets_denses_par_bloc[0] == 1152
    assert mesures.octets_denses_par_bloc[1] == 1152 + 4096


def test_experts_dominent_le_bloc_sans_le_remplir() -> None:
    """Le rapport qui motive tout : l'essentiel du bloc est déportable, une part fine ne l'est pas."""
    mesures = _mesures_moe()

    for total, experts in zip(mesures.octets_par_bloc, mesures.octets_experts_par_bloc, strict=True):
        assert 0 < experts < total, "un bloc ne doit être ni sans experts ni fait que d'experts"


def test_total_du_bloc_inchange_par_la_nouvelle_mesure() -> None:
    """Isoler les experts n'a pas bougé d'un octet le poids total mesuré par bloc."""
    mesures = _mesures_moe()

    assert mesures.octets_par_bloc == [
        OCTETS_EXPERTS_PAR_BLOC + OCTETS_DENSE_PAR_BLOC + (OCTETS_ATTENTION_PAR_BLOC if bloc in BLOCS_ATTENTION else 0)
        for bloc in range(NB_BLOCS)
    ]
    assert mesures.octets_hors_blocs == OCTETS_HORS_BLOCS
    assert mesures.octets_totaux == mesures.octets_hors_blocs + sum(mesures.octets_par_bloc)
    assert mesures.complet is True


def test_modele_sans_experts_mesure_zero_octet_dexperts() -> None:
    """Un dense n'a aucun tenseur d'experts : la liste existe, remplie de zéros, alignée sur les blocs."""
    mesures = depuis_entete(entete_en_memoire(cles_denses(), tenseurs_denses())).mesures

    assert mesures is not None
    assert mesures.octets_experts_par_bloc == [0, 0]
    assert mesures.octets_experts_totaux == 0
    assert mesures.octets_denses_par_bloc == mesures.octets_par_bloc


# ----------------------------------------------------------------- blocs qui portent une attention


def test_blocs_avec_attention_sont_ceux_qui_portent_la_projection() -> None:
    """Une couche sur deux ici, une sur quatre sur le modèle réel : 10 blocs sur 40, pas 40."""
    mesures = _mesures_moe()

    assert mesures.blocs_avec_attention == list(BLOCS_ATTENTION)
    assert len(mesures.blocs_avec_attention) < NB_BLOCS


def test_type_ggml_inconnu_n_efface_pas_le_releve_dattention() -> None:
    """Un poids dont la taille est incalculable porte quand même une attention : le bloc reste compté."""
    illisible = InfoTenseur(nom="blk.0.attn_q.weight", dimensions=(4, 4), type_ggml=250, offset_octets=0)

    mesures = depuis_entete(entete_en_memoire(cles_moe(), [*tenseurs_moe(), illisible])).mesures

    assert mesures is not None
    assert mesures.types_ggml_inconnus == [250]
    assert mesures.complet is False
    assert 0 in mesures.blocs_avec_attention


# --------------------------------------------------------------------------------- invariants


def test_listes_par_bloc_desalignees_refusees() -> None:
    """Un décalage d'un cran attribuerait les experts d'un bloc à son voisin, sans rien signaler."""
    with pytest.raises(ValidationError):
        MesuresTenseurs(
            octets_par_bloc=[10, 20, 30],
            octets_experts_par_bloc=[5, 10],
            blocs_avec_attention=[],
            octets_hors_blocs=0,
            octets_totaux=60,
            blocs_observes=3,
        )
