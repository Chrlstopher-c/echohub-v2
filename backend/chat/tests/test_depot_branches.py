"""Persistance des branches : ce qui est écrit, ce qui reste lisible, ce qui bascule.

Le point vérifié en priorité : rien ne disparaît. Après un rejeu ou une édition, l'arbre contient
toujours l'ancienne branche, avec sa réponse.
"""

from __future__ import annotations

from pathlib import Path

from backend.chat import depot
from backend.chat.modeles import ResumeConversation


def echange(conversation_id: str, question: str, reponse: str) -> tuple[str, str]:
    """Écrit un tour complet chaîné sur la feuille courante et rend (id_user, id_assistant)."""
    utilisateur = depot.ajouter_message(
        conversation_id, role="user", contenu=question, parent_id=depot.feuille_active(conversation_id)
    )
    assistant = depot.ajouter_message(
        conversation_id, role="assistant", contenu=reponse, parent_id=utilisateur.id
    )
    return utilisateur.id, assistant.id


def test_conversation_lineaire_se_lit_comme_avant(conversation: ResumeConversation) -> None:
    echange(conversation.id, "bonjour", "salut")
    echange(conversation.id, "et ensuite ?", "voilà")
    assert [m.contenu for m in depot.lister_messages(conversation.id)] == [
        "bonjour",
        "salut",
        "et ensuite ?",
        "voilà",
    ]


def test_rejeu_d_une_reponse_cree_une_soeur_sans_rien_effacer(conversation: ResumeConversation) -> None:
    question, premiere = echange(conversation.id, "bonjour", "salut")
    seconde = depot.ajouter_message(
        conversation.id, role="assistant", contenu="rebonjour", parent_id=question
    )

    arbre = depot.lire_arbre(conversation.id)
    assert {m.id for m in arbre.messages} == {question, premiere, seconde.id}

    branche = depot.lire_branche(conversation.id)
    assert [m.id for m in branche.messages] == [question, seconde.id]
    assert branche.variantes[seconde.id] == [premiere, seconde.id]


def test_edition_ouvre_une_branche_et_conserve_l_original(conversation: ResumeConversation) -> None:
    question, reponse = echange(conversation.id, "bonjur", "je ne comprends pas")
    corrige = depot.ajouter_message(conversation.id, role="user", contenu="bonjour", parent_id=None)

    branche = depot.lire_branche(conversation.id)
    assert [m.contenu for m in branche.messages] == ["bonjour"]
    assert branche.variantes[corrige.id] == [question, corrige.id]

    conserves = {m.id for m in depot.lire_arbre(conversation.id).messages}
    assert conserves == {question, reponse, corrige.id}


def test_activer_branche_revient_sur_l_ancienne_et_redescend(conversation: ResumeConversation) -> None:
    question, premiere = echange(conversation.id, "bonjour", "salut")
    depot.ajouter_message(conversation.id, role="assistant", contenu="rebonjour", parent_id=question)

    revenue = depot.activer_branche(conversation.id, premiere)
    assert [m.id for m in revenue.messages] == [question, premiere]
    assert depot.feuille_active(conversation.id) == premiere


def test_un_message_ecrit_apres_bascule_prolonge_la_branche_choisie(conversation: ResumeConversation) -> None:
    question, premiere = echange(conversation.id, "bonjour", "salut")
    autre = depot.ajouter_message(
        conversation.id, role="assistant", contenu="rebonjour", parent_id=question
    )
    depot.activer_branche(conversation.id, premiere)

    suite = depot.ajouter_message(
        conversation.id, role="user", contenu="suite", parent_id=depot.feuille_active(conversation.id)
    )
    assert suite.parent_id == premiere
    assert [m.id for m in depot.lister_messages(conversation.id)] == [question, premiere, suite.id]
    assert autre.id in {m.id for m in depot.lire_arbre(conversation.id).messages}


def test_message_d_une_autre_conversation_est_introuvable(conversation: ResumeConversation, base: Path) -> None:
    from backend.chat.modeles import ReglagesConversation

    voisine = depot.creer_conversation("Voisine", None, ReglagesConversation())
    _, reponse = echange(voisine.id, "bonjour", "salut")
    assert depot.lire_message(conversation.id, reponse) is None


def test_vider_les_messages_efface_la_feuille(conversation: ResumeConversation) -> None:
    echange(conversation.id, "bonjour", "salut")
    assert depot.supprimer_messages(conversation.id) == 2
    assert depot.feuille_active(conversation.id) is None
    assert depot.lister_messages(conversation.id) == []
