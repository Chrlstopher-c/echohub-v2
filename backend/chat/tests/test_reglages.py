"""Fusion des réglages : ce qu'un patch modifie, et surtout ce qu'il ne doit PAS modifier."""

from __future__ import annotations

from backend.chat.modeles import (
    MajParametres,
    MajReglages,
    ParametresEchantillonnage,
    ReglagesConversation,
    fusionner_parametres,
    fusionner_reglages,
)


def test_patch_partiel_ne_reinitialise_pas_les_autres_champs() -> None:
    actuels = ParametresEchantillonnage(temperature=0.2, max_tokens=8192, graine=7)
    fusionnes = fusionner_parametres(actuels, MajParametres(temperature=1.4))
    assert fusionnes.temperature == 1.4
    assert fusionnes.max_tokens == 8192
    assert fusionnes.graine == 7


def test_null_explicite_efface_un_plafond_pose() -> None:
    actuels = ParametresEchantillonnage(max_tokens=512, graine=3)
    fusionnes = fusionner_parametres(actuels, MajParametres.model_validate({"max_tokens": None}))
    assert fusionnes.max_tokens is None
    assert fusionnes.graine == 3


def test_max_tokens_absent_par_defaut() -> None:
    assert ParametresEchantillonnage().max_tokens is None


def test_patch_du_prompt_ne_touche_pas_aux_parametres() -> None:
    actuels = ReglagesConversation(parametres=ParametresEchantillonnage(temperature=0.3, max_tokens=2048))
    fusionnes = fusionner_reglages(actuels, MajReglages(prompt_systeme="Tu es concis."))
    assert fusionnes.prompt_systeme == "Tu es concis."
    assert fusionnes.parametres.temperature == 0.3
    assert fusionnes.parametres.max_tokens == 2048


def test_patch_des_parametres_est_fusionne_champ_par_champ() -> None:
    actuels = ReglagesConversation(parametres=ParametresEchantillonnage(top_k=13, max_tokens=2048))
    fusionnes = fusionner_reglages(actuels, MajReglages(parametres=MajParametres(top_k=5)))
    assert fusionnes.parametres.top_k == 5
    assert fusionnes.parametres.max_tokens == 2048


def test_historique_max_messages_est_effacable() -> None:
    actuels = ReglagesConversation(historique_max_messages=10)
    fusionnes = fusionner_reglages(actuels, MajReglages.model_validate({"historique_max_messages": None}))
    assert fusionnes.historique_max_messages is None


def test_sequences_arret_et_graine_passent_bien_dans_les_reglages() -> None:
    actuels = ReglagesConversation()
    patch = MajReglages(parametres=MajParametres(sequences_arret=["<|fin|>"], graine=42))
    fusionnes = fusionner_reglages(actuels, patch)
    assert fusionnes.parametres.sequences_arret == ["<|fin|>"]
    assert fusionnes.parametres.graine == 42
