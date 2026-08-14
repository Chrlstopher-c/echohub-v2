"""Tests des contrôles de cohérence propres aux MoE hybrides — le déclaré confronté au présent.

Chaque contrôle nomme un écart qui, sans lui, se traduisait par un plan silencieusement faux :

- une largeur FFN indéterminée faisait échouer la construction de la cible sans dire laquelle des
  deux clés manquait ;
- une branche partagée présente en tenseurs mais non déclarée en largeur fait une somme incomplète ;
- un `full_attention_interval` qui ne correspond pas aux blocs réellement porteurs d'attention fait
  facturer le cache KV sur le mauvais nombre de couches.

Les trois sont des AVERTISSEMENTS : ils informent le planificateur, ils n'interdisent pas le
chargement. Ce qui est interdit, c'est de continuer sans le savoir.
"""

from __future__ import annotations

from pathlib import Path

from backend.models.coherence import NiveauIncoherence, RapportCoherence, verifier_gguf
from backend.models.gguf_reader import ValeurGGUF

from .fabrique_gguf import ARCHITECTURE_MOE, cles_moe, ecrire_gguf, tenseurs_moe


def _rapport(
    tmp_path: Path,
    surcharges: dict[str, ValeurGGUF | None] | None = None,
    nom: str = "moe.gguf",
) -> RapportCoherence:
    """Écrit un GGUF minuscule puis le vérifie, chaîne complète depuis les octets."""
    chemin = ecrire_gguf(tmp_path / nom, cles_moe(surcharges), tenseurs_moe())
    return verifier_gguf(chemin)


def _codes(rapport: RapportCoherence) -> set[str]:
    return {incoherence.code for incoherence in rapport.incoherences}


def test_moe_de_reference_ne_declenche_aucun_signal(tmp_path: Path) -> None:
    """Un fichier complet et cohérent ne produit rien : sinon les signaux deviennent du bruit."""
    rapport = _rapport(tmp_path)

    assert rapport.incoherences == []
    assert rapport.chargeable is True


def test_largeur_ffn_indeterminee_signalee(tmp_path: Path) -> None:
    """Le cas mesuré : ni `feed_forward_length` ni `expert_feed_forward_length` exploitables."""
    rapport = _rapport(tmp_path, {f"{ARCHITECTURE_MOE}.expert_feed_forward_length": None})

    assert "largeur_ffn_indeterminee" in _codes(rapport)
    assert rapport.chargeable is True, "l'information manque, le fichier n'est pas cassé pour autant"
    signal = next(item for item in rapport.incoherences if item.code == "largeur_ffn_indeterminee")
    assert signal.niveau is NiveauIncoherence.AVERTISSEMENT
    assert "expert" in signal.remediation, "la remédiation doit nommer la substitution à ne pas faire"


def test_largeur_ffn_indeterminee_si_le_nombre_dexperts_actifs_manque(tmp_path: Path) -> None:
    """L'autre moitié du couple : sans `expert_used_count`, la multiplication n'a pas de facteur."""
    rapport = _rapport(tmp_path, {f"{ARCHITECTURE_MOE}.expert_used_count": None})

    assert "largeur_ffn_indeterminee" in _codes(rapport)


def test_expert_partage_sans_largeur_signale(tmp_path: Path) -> None:
    """Des tenseurs `_shexp` existent, leur largeur n'est pas déclarée : la somme est incomplète."""
    rapport = _rapport(tmp_path, {f"{ARCHITECTURE_MOE}.expert_shared_feed_forward_length": None})

    assert "expert_partage_sans_largeur" in _codes(rapport)
    assert rapport.chargeable is True


def test_intervalle_attention_incoherent_signale(tmp_path: Path) -> None:
    """L'intervalle annonce une couche d'attention sur quatre blocs, deux en portent réellement."""
    rapport = _rapport(tmp_path, {f"{ARCHITECTURE_MOE}.full_attention_interval": 4})

    assert "intervalle_attention_incoherent" in _codes(rapport)
    signal = next(item for item in rapport.incoherences if item.code == "intervalle_attention_incoherent")
    assert signal.details["couches_attendues"] == 1
    assert signal.details["couches_observees"] == 2


def test_intervalle_attention_absent_ne_signale_rien(tmp_path: Path) -> None:
    """Sans la clé, il n'y a rien à confronter : on ne fabrique pas un écart avec une valeur supposée."""
    rapport = _rapport(tmp_path, {f"{ARCHITECTURE_MOE}.full_attention_interval": None})

    assert "intervalle_attention_incoherent" not in _codes(rapport)
    assert rapport.incoherences == []


def test_modele_sans_cle_moe_ne_declenche_pas_les_controles_moe(tmp_path: Path) -> None:
    """Retirer `expert_count` retire le sujet : les contrôles MoE ne s'appliquent plus."""
    rapport = _rapport(tmp_path, {f"{ARCHITECTURE_MOE}.expert_count": None})

    assert "largeur_ffn_indeterminee" not in _codes(rapport)
