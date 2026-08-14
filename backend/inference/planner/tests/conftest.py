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
