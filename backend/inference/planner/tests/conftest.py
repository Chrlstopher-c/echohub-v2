"""Fixtures des tests du planificateur — deux modèles et deux machines, tous chiffrés.

Les valeurs ne sont pas inventées : elles reproduisent les deux cas mesurés dans
`COMPATIBILITE-GPU.md`, pour que les tests rejouent exactement les situations où la v1 a échoué.

Aucun GPU, aucun fichier : le planificateur est pur, ses entrées sont des objets.
"""

from __future__ import annotations

import pytest

from backend.inference.planner import (
    DemandeDeChargement,
    FormatModele,
    MetadonneesModele,
    ModeleCharge,
    Moteur,
    Plateforme,
    PreferencesUtilisateur,
    ProfilMachine,
)

MIO = 1024 * 1024
GIO = 1024 * 1024 * 1024

# Poids par couche mesuré sur Qwen3.6-35B-A3B IQ4_XS. La v1 en supposait 150 Mo.
POIDS_COUCHE_MESURE_MIO = 436
COUCHES_REELLES = 41

# --------------------------------------------------------------------------- MoE mesuré
#
# Relevé sur HauhauCS/Qwen3.6-35B-A3B-Uncensored IQ3_M présent sur la machine : 733 tenseurs,
# 40 blocs, architecture `qwen35moe`. Ces nombres ne sont pas des ordres de grandeur choisis pour
# le test, ce sont les mesures — c'est ce qui rend le test capable de contredire le planificateur.
BLOCS_MOE = 40
BLOCS_EXPERTS_LOURDS = 5  # blocs 0 à 4, mesurés plus lourds que les suivants
EXPERTS_BLOC_LOURD_MIO = 364
EXPERTS_BLOC_MIO = 330
# 0,721 Gio de dense pour les 40 blocs. Seul ce TOTAL est mesuré ; la dispersion par bloc ne l'est
# qu'en bornes (15,68 à 19,50 Mio), elle n'est donc pas reproduite ici.
DENSE_BLOC_MIO = 0.721 * 1024 / BLOCS_MOE
# `output.weight` 397,9 Mio en Q6_K + `token_embd` 208,4 Mio en IQ3_S.
HORS_BLOCS_MIO = 606.3
# `{arch}.full_attention_interval` : blocs 3, 7, 11 … 39 seulement portent un cache KV.
INTERVALLE_ATTENTION_MESURE = 4


@pytest.fixture
def modele_grand() -> MetadonneesModele:
    """Qwen3.6-35B-A3B IQ4_XS : 41 couches réelles, 436 Mo par couche, contexte d'entraînement long."""
    return MetadonneesModele(
        identifiant="Qwen3.6-35B-A3B-IQ4_XS",
        format=FormatModele.GGUF,
        architecture="qwen3moe",
        taille_octets=COUCHES_REELLES * POIDS_COUCHE_MESURE_MIO * MIO,
        nombre_couches=COUCHES_REELLES,
        dimension_embedding=2048,
        dimension_ffn=6144,
        nombre_tetes_attention=32,
        nombre_tetes_kv=4,
        dimension_tete=128,
        contexte_entrainement_max=262144,
        taille_vocabulaire=151936,
        quantification="IQ4_XS",
        est_moe=True,
    )


@pytest.fixture
def modele_petit() -> MetadonneesModele:
    """Qwen2.5-0.5B Q4_K_M : tient intégralement en VRAM, contexte compris."""
    return MetadonneesModele(
        identifiant="Qwen2.5-0.5B-Q4_K_M",
        format=FormatModele.GGUF,
        architecture="qwen2",
        taille_octets=400 * MIO,
        nombre_couches=24,
        dimension_embedding=896,
        dimension_ffn=4864,
        nombre_tetes_attention=14,
        nombre_tetes_kv=2,
        dimension_tete=64,
        contexte_entrainement_max=32768,
        taille_vocabulaire=151936,
        quantification="Q4_K_M",
    )


def _poids_mesures_moe() -> tuple[tuple[int, ...], tuple[int, ...], int]:
    """Poids par bloc du MoE mesuré : part experts, part totale, et tenseurs hors blocs."""
    experts = tuple(
        int((EXPERTS_BLOC_LOURD_MIO if index < BLOCS_EXPERTS_LOURDS else EXPERTS_BLOC_MIO) * MIO)
        for index in range(BLOCS_MOE)
    )
    dense = int(DENSE_BLOC_MIO * MIO)
    return experts, tuple(part + dense for part in experts), int(HORS_BLOCS_MIO * MIO)


@pytest.fixture
def modele_moe() -> MetadonneesModele:
    """Qwen3.6-35B-A3B IQ3_M : 90,9 % du poids dans les experts, une couche d'attention sur quatre.

    Deux particularités que le planificateur doit traiter, et qu'aucune autre fixture ne porte :

    - `dimension_ffn` vaut `None` — l'architecture ne déclare pas `feed_forward_length`, seulement
      `expert_feed_forward_length`. Ce champ exigé rendait ce modèle inconstructible, donc non
      planifiable, ce qui est le défaut d'origine ;
    - le poids est relevé bloc par bloc et séparé en dense / experts, ce qui autorise le déport.
    """
    experts, blocs, hors_blocs = _poids_mesures_moe()
    return MetadonneesModele(
        identifiant="Qwen3.6-35B-A3B-IQ3_M",
        format=FormatModele.GGUF,
        architecture="qwen35moe",
        taille_octets=sum(blocs) + hors_blocs,
        nombre_couches=BLOCS_MOE,
        dimension_embedding=2048,
        dimension_ffn=None,
        nombre_tetes_attention=16,
        nombre_tetes_kv=2,
        dimension_tete=256,
        contexte_entrainement_max=262144,
        taille_vocabulaire=248320,
        quantification="IQ3_M",
        est_moe=True,
        nombre_experts=256,
        nombre_experts_actifs=8,
        dimension_ffn_expert=512,
        dimension_ffn_expert_partage=512,
        octets_par_bloc=blocs,
        octets_experts_par_bloc=experts,
        octets_hors_blocs=hors_blocs,
        intervalle_attention_pleine=INTERVALLE_ATTENTION_MESURE,
    )


@pytest.fixture
def modele_moe_sans_mesure(modele_moe: MetadonneesModele) -> MetadonneesModele:
    """Même MoE, mais dont le domaine `models` n'a pas relevé le poids des experts bloc par bloc.

    Cas de repli obligatoire : sans mesure, aucun déport ne peut être décidé, et le planificateur
    doit revenir à la coupe par couches au lieu d'inventer une répartition.
    """
    return modele_moe.model_copy(
        update={"octets_par_bloc": (), "octets_experts_par_bloc": (), "octets_hors_blocs": None}
    )


@pytest.fixture
def modele_safetensors(modele_grand: MetadonneesModele) -> MetadonneesModele:
    """Même modèle au format safetensors : seul vLLM sait le charger, et sans répartition possible."""
    return modele_grand.model_copy(update={"format": FormatModele.SAFETENSORS, "identifiant": "Qwen3.6-35B-AWQ"})


def profil_5080(
    plateforme: Plateforme = Plateforme.WSL2,
    *,
    vram_libre_gio: float = 14.7,
    ram_libre_gio: float = 20.0,
    moteurs: tuple[Moteur, ...] = (Moteur.LLAMA_CPP,),
    charges: tuple[ModeleCharge, ...] = (),
) -> ProfilMachine:
    """RTX 5080 16 Go : ~14,7 Go réellement libres, le bureau Windows occupant le reste."""
    return ProfilMachine(
        plateforme=plateforme,
        index_gpu=0,
        nom_gpu="NVIDIA GeForce RTX 5080",
        vram_totale_octets=16 * GIO,
        vram_libre_octets=int(vram_libre_gio * GIO),
        ram_libre_octets=int(ram_libre_gio * GIO),
        moteurs_disponibles=moteurs,
        modeles_charges=charges,
        capacite_calcul=(12, 0),
    )


def demande(
    metadonnees: MetadonneesModele,
    profil: ProfilMachine | None = None,
    preferences: PreferencesUtilisateur | None = None,
) -> DemandeDeChargement:
    """Raccourci de construction d'une demande complète."""
    return DemandeDeChargement(
        metadonnees=metadonnees,
        profil=profil or profil_5080(),
        preferences=preferences or PreferencesUtilisateur(),
    )
