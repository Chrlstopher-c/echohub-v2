"""Ce que ces tests prouvent : la rotation est équitable, et un moteur qui refuse sort du tirage.

Chaque test fixe l'horloge plutôt que d'attendre : une durée de mise à l'écart se vérifie en
passant l'instant en argument, jamais en dormant trente minutes.
"""

from __future__ import annotations

import pytest

from backend.recherche.modeles import MoteurMuet
from backend.recherche.pool_moteurs import (
    ECART_ALEA_S,
    ECART_BLOCAGE_S,
    POOL_GENERAL,
    TirageMoteurs,
)

_POOL = ("a", "b", "c", "d", "e")


def test_rotation_sert_tout_le_pool_avant_de_recommencer() -> None:
    """Le point entier de la rotation : personne n'est servi deux fois avant que tous l'aient été.

    Un ordre fixe ferait porter toute la charge aux premiers du pool — et face à une ressource
    rationnée, l'inéquité d'un ordre stable n'est pas improbable, elle est certaine.
    """
    tirage = TirageMoteurs(_POOL)
    vus = [nom for _ in range(5) for nom in tirage.choisir(1, horloge=0.0)]
    assert sorted(vus) == sorted(_POOL)


def test_un_moteur_bloque_sort_du_tirage() -> None:
    tirage = TirageMoteurs(_POOL)
    tirage.signaler_muets((MoteurMuet(moteur="c", raison="Suspended: CAPTCHA"),), horloge=0.0)
    vus = [nom for _ in range(8) for nom in tirage.choisir(1, horloge=10.0)]
    assert "c" not in vus


def test_blocage_et_alea_ont_des_durees_distinctes() -> None:
    """Un CAPTCHA est une décision qui dure ; un timeout est un aléa qui ne dit rien de nous."""
    tirage = TirageMoteurs(_POOL)
    tirage.signaler_muets(
        (MoteurMuet(moteur="a", raison="CAPTCHA"), MoteurMuet(moteur="b", raison="timeout")),
        horloge=0.0,
    )
    etat = tirage.etat(horloge=0.0)
    assert etat["a"] == pytest.approx(ECART_BLOCAGE_S)
    assert etat["b"] == pytest.approx(ECART_ALEA_S)
    # L'aléa expire le premier : `b` revient, `a` reste écarté.
    apres = tirage.etat(horloge=ECART_ALEA_S + 1)
    assert "b" not in apres and "a" in apres


def test_pool_entierement_ecarte_tente_quand_meme() -> None:
    """Mieux vaut une recherche qui part vers des moteurs suspendus qu'une recherche qui ne part pas.

    SearXNG dira lui-même qu'ils sont muets — et pendant ce temps un moteur a pu se rétablir sans
    que rien ne nous l'ait annoncé.
    """
    tirage = TirageMoteurs(_POOL)
    tirage.signaler_muets(tuple(MoteurMuet(moteur=n, raison="CAPTCHA") for n in _POOL), horloge=0.0)
    assert tirage.choisir(3, horloge=1.0)


def test_le_pool_de_production_ne_contient_pas_de_doublon() -> None:
    assert len(POOL_GENERAL) == len(set(POOL_GENERAL))


def test_un_pool_vide_est_refuse_a_la_construction() -> None:
    with pytest.raises(ValueError):
        TirageMoteurs(())
