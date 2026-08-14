"""Logique d'arbre — pure, sans base : chemins, feuilles, variantes, garde-fous.

Ces cas rejouent exactement les situations que produit l'interface : rejouer une réponse, éditer
un message, revenir sur une variante. Rien n'y touche SQLite, donc un échec ici désigne la règle
métier et non la persistance.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.chat import branches
from backend.chat.modeles import MessageChat, RoleMessage

_DEPART = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)


def message(identifiant: str, role: RoleMessage, parent: str | None, rang: int) -> MessageChat:
    """Message minimal, horodaté par son rang : l'ordre d'entrée est l'ordre de création."""
    return MessageChat(
        id=identifiant,
        conversation_id="c1",
        role=role,
        contenu=f"contenu {identifiant}",
        cree_le=_DEPART + timedelta(seconds=rang),
        parent_id=parent,
    )


def conversation_avec_variantes() -> list[MessageChat]:
    """u1 → a1, puis un rejeu de a1 en a2, puis une édition de u1 en u2 → a3."""
    return [
        message("u1", "user", None, 0),
        message("a1", "assistant", "u1", 1),
        message("a2", "assistant", "u1", 2),
        message("u2", "user", None, 3),
        message("a3", "assistant", "u2", 4),
    ]


def test_chemin_lineaire_rend_tout_dans_l_ordre() -> None:
    messages = [message("u1", "user", None, 0), message("a1", "assistant", "u1", 1)]
    assert [m.id for m in branches.chemin_vers(messages, "a1")] == ["u1", "a1"]


def test_chemin_ignore_les_branches_soeurs() -> None:
    messages = conversation_avec_variantes()
    assert [m.id for m in branches.chemin_vers(messages, "a1")] == ["u1", "a1"]
    assert [m.id for m in branches.chemin_vers(messages, "a3")] == ["u2", "a3"]


def test_chemin_vide_si_la_feuille_est_inconnue() -> None:
    assert branches.chemin_vers(conversation_avec_variantes(), "inexistant") == []
    assert branches.chemin_vers(conversation_avec_variantes(), None) == []


def test_descendre_suit_la_variante_la_plus_recente() -> None:
    messages = conversation_avec_variantes()
    assert branches.descendre(messages, "u1") == "a2"
    assert branches.descendre(messages, None) == "a3"


def test_feuille_enregistree_prioritaire_sur_la_plus_recente() -> None:
    messages = conversation_avec_variantes()
    assert branches.resoudre_feuille(messages, "a1") == "a1"
    assert branches.resoudre_feuille(messages, None) == "a3"


def test_feuille_disparue_retombe_sur_la_plus_recente() -> None:
    messages = conversation_avec_variantes()
    assert branches.resoudre_feuille(messages, "supprime") == "a3"


def test_feuille_enregistree_redescend_si_un_enfant_a_ete_ecrit_depuis() -> None:
    """Un pointeur resté sur un message qui a depuis reçu une suite ne doit pas tronquer la vue."""
    messages = conversation_avec_variantes()
    assert branches.resoudre_feuille(messages, "u1") == "a2"


def test_variantes_donnent_les_freres_dans_l_ordre() -> None:
    messages = conversation_avec_variantes()
    chemin = branches.chemin_vers(messages, "a2")
    resultat = branches.variantes(messages, chemin)
    assert resultat["a2"] == ["a1", "a2"]
    assert resultat["u1"] == ["u1", "u2"]


def test_cycle_de_parente_ne_boucle_pas() -> None:
    """Une parenté circulaire en base doit tronquer le chemin, jamais figer la requête."""
    boucle = [
        message("x", "user", "y", 0),
        message("y", "assistant", "x", 1),
    ]
    chemin = branches.chemin_vers(boucle, "y")
    assert [m.id for m in chemin] == ["x", "y"]


def test_conversation_vide_n_a_pas_de_feuille() -> None:
    assert branches.resoudre_feuille([], None) is None
