"""Décomposition de la fenêtre de contexte — découpage, cumul, pourcentages.

Aucun modèle, aucun tokenizer, aucun GPU : les décomptes sont injectés. C'est précisément ce qui
rend ces règles vérifiables, alors que le comptage réel exige une carte et plusieurs gigaoctets.

Ce qui est vérifié ici est ce qui pourrait mentir sans qu'on le voie : un caractère perdu au
découpage, un poste oublié dans le cumul, un pourcentage rapporté à la mauvaise référence.
"""

from __future__ import annotations

import pytest

from backend.inference.engines_adapters.contrat import (
    MessageChat,
    MoteurSupporte,
    PosteContexte,
    SegmentContexte,
    assembler_occupation,
    decouper_segments,
    separer_raisonnement,
)


def _tokens(occupation: object, poste: PosteContexte) -> int:
    """Tokens d'un poste dans une occupation, ou -1 si le poste est absent de la légende."""
    postes = getattr(occupation, "postes")
    for part in postes:
        if part.poste is poste:
            return part.tokens
    return -1


# --------------------------------------------------------------- séparation du raisonnement


def test_sans_balise_tout_est_visible() -> None:
    visible, raisonnement = separer_raisonnement("Bonjour, voici la réponse.")
    assert visible == "Bonjour, voici la réponse."
    assert raisonnement == ""


def test_bloc_ferme_est_extrait_avec_ses_balises() -> None:
    # Les balises repartent au moteur au tour suivant : elles coûtent des tokens, elles restent
    # donc dans la part raisonnement plutôt que d'être escamotées.
    visible, raisonnement = separer_raisonnement("<think>je réfléchis</think>Réponse.")
    assert visible == "Réponse."
    assert raisonnement == "<think>je réfléchis</think>"


def test_blocs_multiples_sont_cumules_sans_perte() -> None:
    contenu = "a<think>un</think>b<think>deux</think>c"
    visible, raisonnement = separer_raisonnement(contenu)
    assert visible == "abc"
    assert raisonnement == "<think>un</think><think>deux</think>"
    assert len(visible) + len(raisonnement) == len(contenu)


def test_bloc_jamais_referme_court_jusqu_a_la_fin() -> None:
    # Génération interrompue en plein raisonnement : c'est bien tout le reste que le moteur relira.
    visible, raisonnement = separer_raisonnement("début<think>coupé au milieu")
    assert visible == "début"
    assert raisonnement == "<think>coupé au milieu"


def test_balise_fermante_orpheline_reste_visible() -> None:
    # Pas d'ouverture, donc pas de bloc : on ne devine pas un raisonnement qui n'est pas balisé.
    visible, raisonnement = separer_raisonnement("texte</think>suite")
    assert visible == "texte</think>suite"
    assert raisonnement == ""


@pytest.mark.parametrize(
    "contenu",
    ["", "simple", "<think>a</think>", "x<think>a</think>y<think>b", "<think></think>"],
)
def test_aucun_caractere_perdu(contenu: str) -> None:
    """Invariant central : la somme des deux parts fait toujours le texte d'origine."""
    visible, raisonnement = separer_raisonnement(contenu)
    assert len(visible) + len(raisonnement) == len(contenu)


# ------------------------------------------------------------------------ découpage


def test_prompt_systeme_devient_un_segment() -> None:
    segments = decouper_segments("Tu es concis.", [])
    assert [(s.poste, s.texte) for s in segments] == [(PosteContexte.SYSTEME, "Tu es concis.")]


def test_prompt_systeme_vide_ne_produit_pas_de_segment() -> None:
    assert decouper_segments("", []) == []


def test_roles_sont_ranges_dans_leurs_postes() -> None:
    messages = [
        MessageChat(role="system", content="règle"),
        MessageChat(role="user", content="question"),
        MessageChat(role="assistant", content="réponse"),
    ]
    segments = decouper_segments("", messages)
    assert [s.poste for s in segments] == [
        PosteContexte.SYSTEME,
        PosteContexte.UTILISATEUR,
        PosteContexte.ASSISTANT,
    ]


def test_message_assistant_est_scinde_en_deux_postes() -> None:
    messages = [MessageChat(role="assistant", content="<think>hmm</think>voilà")]
    segments = decouper_segments("", messages)
    assert [(s.poste, s.texte) for s in segments] == [
        (PosteContexte.ASSISTANT, "voilà"),
        (PosteContexte.RAISONNEMENT, "<think>hmm</think>"),
    ]


def test_assistant_purement_raisonnement_ne_produit_pas_de_segment_vide() -> None:
    segments = decouper_segments("", [MessageChat(role="assistant", content="<think>a</think>")])
    assert [s.poste for s in segments] == [PosteContexte.RAISONNEMENT]


def test_message_vide_est_ignore() -> None:
    # Un texte vide coûterait un aller-retour vers le tokenizer pour un zéro connu d'avance.
    assert decouper_segments("", [MessageChat(role="user", content="")]) == []


# -------------------------------------------------------------------------- assemblage


def _segments_types() -> list[SegmentContexte]:
    return [
        SegmentContexte(poste=PosteContexte.SYSTEME, texte="s"),
        SegmentContexte(poste=PosteContexte.UTILISATEUR, texte="u1"),
        SegmentContexte(poste=PosteContexte.ASSISTANT, texte="a"),
        SegmentContexte(poste=PosteContexte.RAISONNEMENT, texte="r"),
        SegmentContexte(poste=PosteContexte.UTILISATEUR, texte="u2"),
    ]


def test_cumul_par_poste_et_espace_libre() -> None:
    occupation = assembler_occupation(_segments_types(), [100, 200, 300, 400, 50], contexte_total=2_000)
    assert occupation.mesurable is True
    assert occupation.tokens_mesures == 1_050
    assert occupation.tokens_libres == 950
    assert occupation.depassement_tokens == 0
    assert _tokens(occupation, PosteContexte.UTILISATEUR) == 250  # deux messages cumulés
    assert _tokens(occupation, PosteContexte.RAISONNEMENT) == 400
    assert _tokens(occupation, PosteContexte.LIBRE) == 950


def test_nombre_de_segments_par_poste() -> None:
    occupation = assembler_occupation(_segments_types(), [1, 1, 1, 1, 1], contexte_total=100)
    parts = {part.poste: part.segments for part in occupation.postes}
    assert parts[PosteContexte.UTILISATEUR] == 2
    assert parts[PosteContexte.SYSTEME] == 1


def test_pourcentages_rapportes_au_contexte_total() -> None:
    occupation = assembler_occupation(
        [SegmentContexte(poste=PosteContexte.UTILISATEUR, texte="u")], [8_192], contexte_total=32_768
    )
    parts = {part.poste: part.part for part in occupation.postes}
    assert parts[PosteContexte.UTILISATEUR] == pytest.approx(0.25)
    assert parts[PosteContexte.LIBRE] == pytest.approx(0.75)
    assert sum(parts.values()) == pytest.approx(1.0)


def test_postes_vides_absents_sauf_espace_libre() -> None:
    # La légende ne montre que ce qui a été mesuré ; `libre` reste, même à zéro, parce que sa
    # disparition rendrait la saturation invisible.
    occupation = assembler_occupation(
        [SegmentContexte(poste=PosteContexte.UTILISATEUR, texte="u")], [10], contexte_total=10
    )
    assert [part.poste for part in occupation.postes] == [PosteContexte.UTILISATEUR, PosteContexte.LIBRE]
    assert _tokens(occupation, PosteContexte.LIBRE) == 0


def test_ordre_des_postes_est_stable() -> None:
    occupation = assembler_occupation(_segments_types(), [1, 2, 3, 4, 5], contexte_total=1_000)
    assert [part.poste for part in occupation.postes] == [
        PosteContexte.SYSTEME,
        PosteContexte.UTILISATEUR,
        PosteContexte.RAISONNEMENT,
        PosteContexte.ASSISTANT,
        PosteContexte.LIBRE,
    ]


def test_depassement_de_fenetre_est_chiffre_sans_libre_negatif() -> None:
    occupation = assembler_occupation(
        [SegmentContexte(poste=PosteContexte.UTILISATEUR, texte="u")], [40_000], contexte_total=32_768
    )
    assert occupation.tokens_libres == 0
    assert occupation.depassement_tokens == 40_000 - 32_768
    assert occupation.tokens_mesures == 40_000


def test_ecart_entre_plan_et_contexte_servi_est_signale() -> None:
    # Le moteur fait foi : c'est lui qui est mesuré. L'écart se dit, il ne se corrige pas.
    occupation = assembler_occupation(
        [SegmentContexte(poste=PosteContexte.UTILISATEUR, texte="u")],
        [10],
        contexte_total=32_768,
        contexte_plan=57_344,
        moteur=MoteurSupporte.LLAMA_CPP,
        modele="Qwen3.6-35B-A3B",
    )
    assert occupation.contexte_total == 32_768
    assert occupation.contexte_plan == 57_344
    assert any("32768" in ligne for ligne in occupation.avertissements)


def test_surcout_du_gabarit_est_declare_non_mesure() -> None:
    occupation = assembler_occupation([], [], contexte_total=4_096)
    assert any("Non compté" in ligne for ligne in occupation.avertissements)


def test_conversation_vide_laisse_toute_la_fenetre_libre() -> None:
    occupation = assembler_occupation([], [], contexte_total=4_096)
    assert occupation.tokens_mesures == 0
    assert _tokens(occupation, PosteContexte.LIBRE) == 4_096


def test_decompte_incoherent_est_refuse() -> None:
    # Un décalage segments/valeurs attribuerait des tokens au mauvais poste, en silence.
    with pytest.raises(ValueError, match="incohérent"):
        assembler_occupation(_segments_types(), [1, 2], contexte_total=1_000)
