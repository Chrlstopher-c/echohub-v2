"""Tests de la déduction de capacités — jeux d'étiquettes en dur, aucun appel réseau.

Ce que ces tests protègent, dans l'ordre d'importance :

1. **la traçabilité** : une capacité sans indice ne doit jamais exister, et l'indice doit nommer la
   déclaration exacte qui a conclu. C'est ce qui distingue une inférence assumée d'une invention ;
2. **le silence** : un dépôt qui n'annonce rien produit une liste vide. La v1 remplissait ce vide
   avec des valeurs dérivées d'un nom, et se trompait ;
3. **la précision des règles** : correspondance exacte sur les étiquettes, mots entiers sur les
   textes libres, pour qu'un dépôt de génération d'images ne passe pas pour un modèle de vision.
"""

from __future__ import annotations

import pytest

from backend.models.capacites import (
    REGLES,
    Capacite,
    CapaciteDeduite,
    SignauxDepot,
    SourceIndice,
    deduire_capacites,
    definitions,
    possede_toutes,
)


def _capacites(deduites: list[CapaciteDeduite]) -> set[Capacite]:
    """Ensemble des capacités, sans leurs indices — pour les assertions qui portent sur le quoi."""
    return {deduite.capacite for deduite in deduites}


def _indices(deduites: list[CapaciteDeduite], capacite: Capacite) -> set[tuple[SourceIndice, str]]:
    """Provenance d'une capacité donnée, sous forme comparable."""
    for deduite in deduites:
        if deduite.capacite is capacite:
            return {(indice.source, indice.valeur) for indice in deduite.indices}
    return set()


# ------------------------------------------------------------------ ce que le Hub annonce vraiment


def test_vision_deduite_de_la_tache_et_tracee() -> None:
    """`image-text-to-text` est la déclaration la plus structurée du Hub : elle doit conclure seule."""
    deduites = deduire_capacites(
        SignauxDepot(
            depot="Qwen/Qwen3-VL-8B-Instruct",
            tache="image-text-to-text",
            etiquettes=["transformers", "image-text-to-text", "conversational"],
        )
    )

    assert Capacite.VISION in _capacites(deduites)
    provenance = _indices(deduites, Capacite.VISION)
    assert (SourceIndice.TACHE, "image-text-to-text") in provenance
    assert (SourceIndice.ETIQUETTE, "image-text-to-text") in provenance
    assert (SourceIndice.NOM, "vl") in provenance


def test_projecteur_mmproj_suffit_a_conclure_a_la_vision() -> None:
    """Un dépôt GGUF sans étiquette utile : seul le projecteur listé signale la tour de vision."""
    deduites = deduire_capacites(
        SignauxDepot(
            depot="bartowski/Modele-Quelconque-GGUF",
            fichiers=["Modele-Quelconque-Q4_K_M.gguf", "mmproj-model-f16.gguf"],
        )
    )

    assert _capacites(deduites) == {Capacite.VISION}
    assert _indices(deduites, Capacite.VISION) == {(SourceIndice.FICHIER, "mmproj-model-f16.gguf")}


def test_raisonnement_et_sans_censure_deduits_du_nom() -> None:
    """Le modèle réellement présent sur la machine : « Uncensored » est une déclaration d'auteur."""
    deduites = deduire_capacites(SignauxDepot(depot="HauhauCS/Qwen3.6-35B-A3B-Uncensored-Thinking"))

    assert _capacites(deduites) == {Capacite.RAISONNEMENT, Capacite.SANS_CENSURE}
    assert _indices(deduites, Capacite.SANS_CENSURE) == {(SourceIndice.NOM, "uncensored")}
    assert _indices(deduites, Capacite.RAISONNEMENT) == {(SourceIndice.NOM, "thinking")}


def test_separateurs_du_nom_ne_masquent_pas_un_signal() -> None:
    """`_` est un caractère de mot : sans normalisation, `Qwen3_VL` échapperait au motif `\\bvl\\b`."""
    souligne = deduire_capacites(SignauxDepot(depot="essai/Qwen3_VL_8B"))
    tiret = deduire_capacites(SignauxDepot(depot="essai/Qwen3-VL-8B"))

    assert _capacites(souligne) == _capacites(tiret) == {Capacite.VISION}


def test_description_est_une_source_a_part_entiere() -> None:
    """Un texte libre conclut comme le reste, mais la source le dit — l'appelant peut en tenir compte."""
    deduites = deduire_capacites(
        SignauxDepot(depot="essai/Modele", description="Ce modèle prend en charge le function-calling.")
    )

    assert _indices(deduites, Capacite.APPEL_OUTILS) == {(SourceIndice.DESCRIPTION, "function-calling")}


def test_auteur_du_depot_ignore() -> None:
    """Un compte de reconditionnement publie de tout : son nom n'apprend rien sur ce modèle-ci."""
    deduites = deduire_capacites(SignauxDepot(depot="TheVisionCoder/Modele-Neutre"))

    assert _capacites(deduites) == set()


# ---------------------------------------------------------------------------- silence et précision


def test_depot_sans_signal_ne_produit_aucune_capacite() -> None:
    """Régression v1 : un dépôt banal ne doit rien inspirer. L'absence se rend telle quelle."""
    deduites = deduire_capacites(
        SignauxDepot(
            depot="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
            tache="text-generation",
            etiquettes=["transformers", "text-generation", "conversational", "en", "license:apache-2.0"],
            fichiers=["qwen2.5-0.5b-instruct-q4_k_m.gguf", "README.md"],
        )
    )

    assert deduites == []


def test_generation_image_ne_deborde_pas_sur_la_vision() -> None:
    """Produire des images et comprendre des images sont deux capacités distinctes, jamais confondues."""
    deduites = deduire_capacites(
        SignauxDepot(
            depot="black-forest-labs/FLUX.1-dev",
            tache="text-to-image",
            etiquettes=["diffusers", "text-to-image"],
        )
    )

    assert _capacites(deduites) == {Capacite.GENERATION_IMAGE}


def test_etiquettes_comparees_exactement() -> None:
    """Correspondance exacte : une étiquette voisine n'est pas l'étiquette, et ne conclut pas."""
    deduites = deduire_capacites(SignauxDepot(depot="essai/Modele", etiquettes=["text-to-image-adapter"]))

    assert deduites == []


def test_casse_des_etiquettes_sans_effet() -> None:
    """Le Hub publie des slugs minuscules, mais rien ne l'y oblige : la comparaison normalise."""
    deduites = deduire_capacites(SignauxDepot(depot="essai/Modele", etiquettes=["Uncensored"]))

    assert _indices(deduites, Capacite.SANS_CENSURE) == {(SourceIndice.ETIQUETTE, "uncensored")}


def test_indices_dedupliques_entre_sources() -> None:
    """Une même valeur répétée ne gonfle pas la provenance ; deux sources distinctes la nourrissent."""
    deduites = deduire_capacites(
        SignauxDepot(
            depot="essai/Modele-Uncensored",
            etiquettes=["uncensored", "uncensored", "abliterated"],
        )
    )

    assert _indices(deduites, Capacite.SANS_CENSURE) == {
        (SourceIndice.ETIQUETTE, "abliterated"),
        (SourceIndice.ETIQUETTE, "uncensored"),
        (SourceIndice.NOM, "uncensored"),
    }


def test_deduction_deterministe() -> None:
    """Deux appels identiques rendent exactement la même liste : les tests et le cache en dépendent."""
    signaux = SignauxDepot(
        depot="Qwen/Qwen3-VL-30B-Thinking",
        tache="image-text-to-text",
        etiquettes=["vision", "reasoning", "tools"],
    )

    assert deduire_capacites(signaux) == deduire_capacites(signaux)


@pytest.mark.parametrize(
    ("etiquettes", "attendue"),
    [
        (["tool-calling"], Capacite.APPEL_OUTILS),
        (["automatic-speech-recognition"], Capacite.AUDIO_ENTREE),
        (["text-to-speech"], Capacite.AUDIO_SORTIE),
        (["code-generation"], Capacite.CODE),
        (["sentence-transformers"], Capacite.EMBEDDINGS),
    ],
)
def test_etiquette_unique_conclut_a_la_bonne_capacite(etiquettes: list[str], attendue: Capacite) -> None:
    """Chaque famille d'étiquettes tombe dans la bonne case, et dans elle seule."""
    deduites = deduire_capacites(SignauxDepot(depot="essai/Modele", etiquettes=etiquettes))

    assert _capacites(deduites) == {attendue}


# ------------------------------------------------------------------------ invariants du vocabulaire


def test_toute_capacite_deduite_porte_au_moins_un_indice() -> None:
    """L'invariant central : pas d'indice, pas de capacité. Il est structurel, on le vérifie quand même."""
    deduites = deduire_capacites(
        SignauxDepot(
            depot="essai/Qwen-VL-Coder-Thinking-Uncensored",
            tache="image-text-to-text",
            etiquettes=["tools", "tts", "embeddings", "text-to-image", "whisper"],
            fichiers=["mmproj.gguf"],
        )
    )

    assert len(deduites) == len(Capacite), "ce dépôt fictif déclare tout le vocabulaire"
    assert all(deduite.indices for deduite in deduites)


def test_chaque_capacite_a_une_definition_et_des_regles() -> None:
    """Ajouter une capacité sans l'écrire ni la détecter la rendrait invisible ou muette."""
    decrites = {definition.capacite for definition in definitions()}

    assert decrites == set(Capacite)
    assert set(REGLES) == set(Capacite)


def test_valeurs_de_capacite_stables() -> None:
    """Ces chaînes voyagent dans l'URL de recherche : les renommer casse le frontend en silence."""
    assert {capacite.value for capacite in Capacite} == {
        "raisonnement",
        "appel_outils",
        "vision",
        "generation_image",
        "audio_entree",
        "audio_sortie",
        "code",
        "embeddings",
        "sans_censure",
    }


# ------------------------------------------------------------------------------- filtre combiné ET


def test_filtre_exige_toutes_les_capacites() -> None:
    """Combiner deux filtres cherche un modèle qui fait les deux, pas l'un OU l'autre."""
    deduites = deduire_capacites(
        SignauxDepot(depot="Qwen/Qwen3-VL-Thinking", tache="image-text-to-text")
    )

    assert possede_toutes(deduites, [Capacite.VISION]) is True
    assert possede_toutes(deduites, [Capacite.VISION, Capacite.RAISONNEMENT]) is True
    assert possede_toutes(deduites, [Capacite.VISION, Capacite.APPEL_OUTILS]) is False


def test_filtre_vide_ne_retire_rien() -> None:
    """Aucun filtre demandé : la recherche doit se comporter exactement comme avant leur existence."""
    assert possede_toutes([], []) is True
