"""Tests de la lecture des métadonnées d'un MoE hybride — clés lues, clés absentes, rien d'inventé.

Ce que ces tests protègent, dans l'ordre d'importance :

1. **l'absence reste une absence** : `{arch}.feed_forward_length` n'existe pas sur `qwen35moe`, et
   `longueur_feed_forward` doit rester `None`. Y recopier `expert_feed_forward_length` rendrait la
   cible de chargement constructible en la sous-dimensionnant d'un facteur 8 — un plan faux qui
   fonctionne est plus coûteux qu'un plan qui refuse ;
2. **la largeur vive est une somme complète ou rien** : `nb_experts_actifs × largeur d'un expert` plus
   la branche partagée. Un terme manquant rend `None`, jamais une moitié de somme ;
3. **les clés non observées restent nulles** : `expert_shared_count`, `leading_dense_block_count` ne
   sont sur aucun des deux fichiers de la machine ; elles se lisent si elles sont là, pas autrement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.errors import MetadonneesIllisibles
from backend.models.gguf_metadata import MetadonneesGGUF, depuis_entete, lire_metadonnees
from backend.models.gguf_reader import ValeurGGUF

from .fabrique_gguf import (
    ARCHITECTURE_MOE,
    LARGEUR_EXPERT,
    LARGEUR_PARTAGEE,
    NB_EXPERTS,
    NB_EXPERTS_ACTIFS,
    cles_denses,
    cles_moe,
    ecrire_gguf,
    entete_en_memoire,
    tenseurs_denses,
    tenseurs_moe,
)


def _metadonnees_moe(surcharges: dict[str, ValeurGGUF | None] | None = None) -> MetadonneesGGUF:
    """Métadonnées du MoE de référence, éventuellement privé d'une clé."""
    return depuis_entete(entete_en_memoire(cles_moe(surcharges), tenseurs_moe()))


# ------------------------------------------------------- l'absence de `feed_forward_length` reste une absence


def test_feed_forward_length_absente_reste_none() -> None:
    """Le cas exact qui bloquait le modèle réel : la clé n'existe pas, le champ vaut `None`."""
    metadonnees = _metadonnees_moe()

    assert f"{ARCHITECTURE_MOE}.feed_forward_length" not in cles_moe()
    assert metadonnees.longueur_feed_forward is None


def test_largeur_expert_n_est_pas_recopiee_dans_feed_forward_length() -> None:
    """La substitution interdite : deux grandeurs différentes ne partagent pas un champ."""
    metadonnees = _metadonnees_moe()

    assert metadonnees.experts.largeur_ffn_expert == LARGEUR_EXPERT
    assert metadonnees.longueur_feed_forward != LARGEUR_EXPERT


def test_feed_forward_length_presente_est_rendue_telle_quelle() -> None:
    """Quand la clé existe, le champ la reflète sans transformation."""
    metadonnees = depuis_entete(entete_en_memoire(cles_denses(), tenseurs_denses()))

    assert metadonnees.longueur_feed_forward == 64


# ------------------------------------------------------------------------- clés du mélange d'experts


def test_cles_moe_declarees_sont_lues() -> None:
    """Chaque clé présente arrive dans son champ, y compris le réel et le booléen."""
    experts = _metadonnees_moe().experts

    assert experts.largeur_ffn_expert == LARGEUR_EXPERT
    assert experts.largeur_ffn_partagee == LARGEUR_PARTAGEE
    assert experts.fonction_routage == 2
    assert experts.echelle_poids == pytest.approx(2.5)
    assert experts.poids_normalises is True


def test_cles_moe_non_declarees_restent_nulles() -> None:
    """Non observées sur les deux fichiers de la machine : aucune ne reçoit de défaut."""
    experts = _metadonnees_moe().experts

    assert experts.nb_experts_partages is None
    assert experts.nb_blocs_denses_en_tete is None


def test_cardinal_des_experts_inchange() -> None:
    """`expert_count` et `expert_used_count` restent là où les appelants les lisaient déjà."""
    metadonnees = _metadonnees_moe()

    assert metadonnees.nb_experts == NB_EXPERTS
    assert metadonnees.nb_experts_actifs == NB_EXPERTS_ACTIFS
    assert metadonnees.est_moe is True


def test_modele_dense_ne_recoit_aucune_valeur_moe() -> None:
    """Aucune clé MoE dans le fichier : tous les champs correspondants restent nuls."""
    metadonnees = depuis_entete(entete_en_memoire(cles_denses(), tenseurs_denses()))

    assert metadonnees.est_moe is False
    assert metadonnees.experts.largeur_ffn_expert is None
    assert metadonnees.experts.largeur_ffn_partagee is None
    assert metadonnees.experts.poids_normalises is None


# ------------------------------------------------------------------------------ largeur FFN vive


def test_largeur_ffn_active_multiplie_par_les_experts_actifs() -> None:
    """2 experts actifs de largeur 16, plus une branche partagée de 8 : 40, et surtout pas 16."""
    metadonnees = _metadonnees_moe()

    assert metadonnees.largeur_ffn_active == NB_EXPERTS_ACTIFS * LARGEUR_EXPERT + LARGEUR_PARTAGEE
    assert metadonnees.largeur_ffn_active == 40
    assert metadonnees.largeur_ffn_active != LARGEUR_EXPERT, "le piège de substitution, figé ici"


def test_largeur_ffn_active_nulle_si_la_largeur_dun_expert_manque() -> None:
    """Un terme manquant ne se complète pas : la somme n'existe pas, l'appelant décide."""
    metadonnees = _metadonnees_moe({f"{ARCHITECTURE_MOE}.expert_feed_forward_length": None})

    assert metadonnees.largeur_ffn_active is None


def test_largeur_ffn_active_nulle_si_le_nombre_dexperts_actifs_manque() -> None:
    """Sans `expert_used_count`, le facteur de la multiplication est inconnu."""
    metadonnees = _metadonnees_moe({f"{ARCHITECTURE_MOE}.expert_used_count": None})

    assert metadonnees.largeur_ffn_active is None


def test_largeur_ffn_active_sans_branche_partagee_declaree() -> None:
    """Branche partagée non déclarée : elle ne compte pas, et le reste de la somme tient."""
    metadonnees = _metadonnees_moe({f"{ARCHITECTURE_MOE}.expert_shared_feed_forward_length": None})

    assert metadonnees.largeur_ffn_active == NB_EXPERTS_ACTIFS * LARGEUR_EXPERT


def test_largeur_ffn_active_dun_modele_dense_est_la_cle_lue() -> None:
    """Hors MoE, la largeur vive est exactement `feed_forward_length`, sans détour."""
    metadonnees = depuis_entete(entete_en_memoire(cles_denses(), tenseurs_denses()))

    assert metadonnees.largeur_ffn_active == metadonnees.longueur_feed_forward == 64


def test_largeur_ffn_active_dun_dense_sans_cle_reste_nulle() -> None:
    """Ni MoE ni `feed_forward_length` : rien à rendre, et surtout rien à inventer."""
    metadonnees = depuis_entete(
        entete_en_memoire(cles_denses({"qwen35.feed_forward_length": None}), tenseurs_denses())
    )

    assert metadonnees.largeur_ffn_active is None


# ------------------------------------------------------------- attention hybride, mRoPE et état SSM


def test_intervalle_attention_pleine_lu() -> None:
    """La mesure la plus lourde du fichier : une couche sur N porte un cache KV."""
    metadonnees = _metadonnees_moe()

    assert metadonnees.attention.intervalle_attention_pleine == 2


def test_intervalle_absent_reste_nul() -> None:
    """Sans la clé, le planificateur doit savoir qu'il ne sait pas — pas supposer « toutes »."""
    metadonnees = _metadonnees_moe({f"{ARCHITECTURE_MOE}.full_attention_interval": None})

    assert metadonnees.attention.intervalle_attention_pleine is None


def test_sections_rope_lues() -> None:
    """`rope.dimension_sections` complète la caractérisation du RoPE, jusque-là partielle."""
    metadonnees = _metadonnees_moe()

    assert metadonnees.attention.sections_rope == [3, 3, 2, 0]
    assert metadonnees.attention.dimension_rope == 8


def test_parametres_ssm_lus() -> None:
    """Les cinq clés `ssm.*` : c'est ce qui remplace le cache KV sur les couches sans attention."""
    ssm = _metadonnees_moe().ssm

    assert ssm.dimension_interne == 64
    assert ssm.dimension_etat == 16
    assert ssm.noyau_convolution == 4
    assert ssm.rang_pas_de_temps == 8
    assert ssm.nb_groupes == 2
    assert ssm.declare is True


def test_absence_totale_de_ssm_se_declare_comme_telle() -> None:
    """Un modèle dense ne déclare aucun état récurrent : `declare` est faux, pas « zéro »."""
    metadonnees = depuis_entete(entete_en_memoire(cles_denses(), tenseurs_denses()))

    assert metadonnees.ssm.declare is False
    assert metadonnees.ssm.dimension_interne is None


def test_ssm_partiel_reste_declare() -> None:
    """Une seule clé lue suffit à savoir que l'architecture porte un état récurrent."""
    metadonnees = _metadonnees_moe(
        {
            f"{ARCHITECTURE_MOE}.ssm.state_size": None,
            f"{ARCHITECTURE_MOE}.ssm.conv_kernel": None,
            f"{ARCHITECTURE_MOE}.ssm.time_step_rank": None,
            f"{ARCHITECTURE_MOE}.ssm.group_count": None,
        }
    )

    assert metadonnees.ssm.declare is True
    assert metadonnees.ssm.dimension_etat is None


# --------------------------------------------------------------------- chaîne complète, depuis les octets


def test_lecture_dun_fichier_gguf_reel(tmp_path: Path) -> None:
    """Même résultat en passant par les octets : le lecteur binaire rend bien ces clés-là."""
    chemin = ecrire_gguf(tmp_path / "moe.gguf", cles_moe(), tenseurs_moe())

    metadonnees = lire_metadonnees(chemin)

    assert metadonnees.architecture == ARCHITECTURE_MOE
    assert metadonnees.longueur_feed_forward is None
    assert metadonnees.experts.largeur_ffn_expert == LARGEUR_EXPERT
    assert metadonnees.experts.echelle_poids == pytest.approx(2.5)
    assert metadonnees.attention.sections_rope == [3, 3, 2, 0]
    assert metadonnees.attention.base_rope == pytest.approx(10_000_000.0)
    assert metadonnees.ssm.dimension_interne == 64
    assert metadonnees.largeur_ffn_active == 40


def test_architecture_absente_echoue_explicitement() -> None:
    """Sans `general.architecture`, aucune clé préfixée n'est adressable : on le dit, on ne devine pas."""
    with pytest.raises(MetadonneesIllisibles):
        depuis_entete(entete_en_memoire(cles_moe({"general.architecture": None}), tenseurs_moe()))
