"""Préparation d'un tour : où la réponse s'accroche, et ce qui part réellement au moteur.

`preparer*()` est synchrone et n'ouvre aucun flux : ces cas s'exécutent sans moteur, sans GPU et
sans réseau. Ils vérifient les deux promesses du lot — une branche ouverte ne détruit rien, et les
réglages de la conversation arrivent tels quels dans la requête de génération.
"""

from __future__ import annotations

import pytest

from backend.chat import annulation, depot, generation
from backend.chat.erreurs import BrancheInvalide
from backend.chat.modeles import (
    DemandeEdition,
    DemandeGeneration,
    DemandeRejeu,
    ParametresEchantillonnage,
    ReglagesConversation,
    ResumeConversation,
)


def tour(conversation_id: str, question: str, reponse: str) -> tuple[str, str]:
    """Un échange complet, écrit comme la génération l'écrit : chaîné sur la feuille courante."""
    utilisateur = depot.ajouter_message(
        conversation_id, role="user", contenu=question, parent_id=depot.feuille_active(conversation_id)
    )
    assistant = depot.ajouter_message(
        conversation_id, role="assistant", contenu=reponse, parent_id=utilisateur.id
    )
    return utilisateur.id, assistant.id


def test_envoi_normal_prolonge_la_branche_courante(conversation: ResumeConversation) -> None:
    _, reponse = tour(conversation.id, "bonjour", "salut")
    preparation = generation.preparer(conversation.id, DemandeGeneration(contenu="suite"))

    assert preparation.message_utilisateur_id is not None
    utilisateur = depot.lire_message(conversation.id, preparation.message_utilisateur_id)
    assert utilisateur is not None and utilisateur.parent_id == reponse
    assert preparation.parent_id == utilisateur.id
    assert [m.contenu for m in preparation.requete.messages if m.role != "system"] == ["bonjour", "salut", "suite"]


def test_rejeu_d_une_reponse_repart_de_son_parent(conversation: ResumeConversation) -> None:
    question, ancienne = tour(conversation.id, "bonjour", "salut")
    preparation = generation.preparer_rejeu(conversation.id, ancienne, DemandeRejeu())

    assert preparation.parent_id == question
    assert preparation.message_utilisateur_id is None
    # L'ancienne réponse n'est plus dans le contexte : on rejoue le tour, on ne l'enchaîne pas.
    assert [m.contenu for m in preparation.requete.messages if m.role != "system"] == ["bonjour"]

    # Tant que rien n'est généré, la vue reste sur la branche complète existante : une génération
    # qui échoue ne doit pas laisser l'utilisateur sur une question sans réponse.
    assert depot.feuille_active(conversation.id) == ancienne

    nouvelle = depot.ajouter_message(
        conversation.id, role="assistant", contenu="rebonjour", parent_id=preparation.parent_id
    )
    branche = depot.lire_branche(conversation.id)
    assert [m.id for m in branche.messages] == [question, nouvelle.id]
    assert branche.variantes[nouvelle.id] == [ancienne, nouvelle.id]


def test_rejeu_d_un_message_utilisateur_le_recopie_en_soeur(conversation: ResumeConversation) -> None:
    question, _ = tour(conversation.id, "bonjour", "salut")
    preparation = generation.preparer_rejeu(conversation.id, question, DemandeRejeu())

    copie = preparation.message_utilisateur_id
    assert copie is not None and copie != question
    relu = depot.lire_message(conversation.id, copie)
    assert relu is not None and relu.contenu == "bonjour" and relu.parent_id is None
    assert depot.lire_message(conversation.id, question) is not None


def test_edition_cree_une_branche_et_garde_l_original(conversation: ResumeConversation) -> None:
    question, reponse = tour(conversation.id, "bonjur", "je ne comprends pas")
    preparation = generation.preparer_edition(
        conversation.id, question, DemandeEdition(contenu="bonjour")
    )

    assert [m.contenu for m in preparation.requete.messages if m.role != "system"] == ["bonjour"]
    conserves = {m.id for m in depot.lire_arbre(conversation.id).messages}
    assert {question, reponse} <= conserves


def test_editer_une_reponse_du_modele_est_refuse(conversation: ResumeConversation) -> None:
    _, reponse = tour(conversation.id, "bonjour", "salut")
    with pytest.raises(BrancheInvalide):
        generation.preparer_edition(conversation.id, reponse, DemandeEdition(contenu="autre"))


def test_rejeu_sans_historique_en_amont_est_refuse(conversation: ResumeConversation) -> None:
    """Rejouer une réponse racine ne laisserait rien à envoyer : erreur métier, pas 500."""
    orpheline = depot.ajouter_message(conversation.id, role="assistant", contenu="seule", parent_id=None)
    with pytest.raises(BrancheInvalide):
        generation.preparer_rejeu(conversation.id, orpheline.id, DemandeRejeu())


def test_une_branche_refusee_ne_deplace_pas_la_vue(conversation: ResumeConversation) -> None:
    question, reponse = tour(conversation.id, "bonjour", "salut")
    orpheline = depot.ajouter_message(conversation.id, role="assistant", contenu="seule", parent_id=None)
    depot.definir_feuille_active(conversation.id, reponse)
    annulation.reinitialiser()

    with pytest.raises(BrancheInvalide):
        generation.preparer_rejeu(conversation.id, orpheline.id, DemandeRejeu())
    assert depot.feuille_active(conversation.id) == reponse
    assert question in {m.id for m in depot.lister_messages(conversation.id)}


def test_les_reglages_partent_tels_quels_au_moteur(conversation: ResumeConversation) -> None:
    reglages = ReglagesConversation(
        prompt_systeme="Tu es bref.",
        parametres=ParametresEchantillonnage(
            temperature=0.2,
            top_p=0.5,
            top_k=7,
            penalite_repetition=1.3,
            max_tokens=9000,
            sequences_arret=["<|fin|>"],
            graine=42,
        ),
    )
    depot.ecrire_reglages(conversation.id, reglages)
    preparation = generation.preparer(conversation.id, DemandeGeneration(contenu="bonjour"))

    assert preparation.requete.parametres == reglages.parametres
    # Le prompt de la conversation est CONSERVÉ, mais il n'est plus seul : le socle du harnais le
    # précède dans le même message système, pour que le modèle sache quels outils existent avant
    # d'obéir à sa consigne de style. L'un ne remplace jamais l'autre.
    assert preparation.requete.messages[0].role == "system"
    assert preparation.requete.messages[0].contenu.endswith("Tu es bref.")


def test_parametres_du_tour_surchargent_ceux_de_la_conversation(conversation: ResumeConversation) -> None:
    depot.ecrire_reglages(conversation.id, ReglagesConversation())
    ponctuels = ParametresEchantillonnage(temperature=1.9, max_tokens=64)
    preparation = generation.preparer(
        conversation.id, DemandeGeneration(contenu="bonjour", parametres=ponctuels)
    )
    assert preparation.requete.parametres == ponctuels
