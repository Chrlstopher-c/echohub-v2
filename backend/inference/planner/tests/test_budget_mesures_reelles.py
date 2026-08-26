"""Ce que ces tests figent : des MESURES, pas des intentions.

Toutes les valeurs attendues ici ont été lues le 2026-08-26 dans le journal de llama-server
(`sched_reserve: CUDA0 compute buffer size`, `llama_memory_recurrent: CUDA0 RS buffer size`), sur la
RTX 3060 de la machine, à un seul slot. Elles ne sont pas dérivées d'une lecture du code amont.

Le défaut qu'ils empêchent de revenir : le plan annonçait « Contexte demandé, tenable tel quel » à
262144 tokens, et le GPU refusait l'allocation — `cudaMalloc failed: out of memory` sur 827,69 MiB
de tampons que le budget chiffrait à 205. Un budget qui sous-estime ne se voit pas dans un test
d'unité classique : il se voit à l'échec de chargement, une fois le modèle déjà déchargé.
"""

from __future__ import annotations

import pytest

from backend.inference.planner.budget import octets_etat_recurrent, octets_tampons_calcul
from backend.inference.planner.entrees import MetadonneesModele

_MIO = 1024 * 1024

_COMMUN = dict(
    identifiant="banc", format="gguf", contexte_entrainement_max=262144, contexte_natif=262144,
    taille_vocabulaire=248320, intervalle_attention_pleine=4,
    dimension_interne_ssm=4096, dimension_etat_ssm=128, noyau_convolution_ssm=4,
)


def _modele(couches: int, embedding: int, tetes_kv: int) -> MetadonneesModele:
    return MetadonneesModele(
        taille_octets=11_554_953_280, nombre_couches=couches, dimension_embedding=embedding,
        nombre_tetes_attention=16, nombre_tetes_kv=tetes_kv, dimension_tete=256, **_COMMUN)


_QWEN35B = _modele(40, 2048, 2)
_QWEN9B = _modele(32, 4096, 4)

# (modèle, contexte, MiB relevés au journal). Le 35B à 32768 est le seul point sous le régime
# linéaire : un plancher lié au batch y domine, et le budget le sous-estime de 8,7 MiB — écart
# assumé, absorbé par la réserve de fragmentation, et bien plus petit que les 620 MiB d'avant.
_TAMPONS_MESURES = [
    (_QWEN35B, 65536, 251.69),
    (_QWEN35B, 131072, 443.69),
    (_QWEN35B, 262144, 827.69),
    (_QWEN9B, 65536, 399.66),
    (_QWEN9B, 131072, 719.66),
]


@pytest.mark.parametrize(("modele", "contexte", "mesure_mio"), _TAMPONS_MESURES)
def test_les_tampons_couvrent_ce_que_llama_cpp_alloue(
    modele: MetadonneesModele, contexte: int, mesure_mio: float
) -> None:
    """Couvrir, jamais égaler : un budget juste au MiB près échoue au premier aléa d'allocateur."""
    prevu_mio = octets_tampons_calcul(modele, contexte, 2048, flash_attention=True) / _MIO
    assert prevu_mio >= mesure_mio, f"sous-estimation de {mesure_mio - prevu_mio:.1f} MiB"


def test_les_tampons_croissent_avec_le_contexte_meme_sous_flash_attention() -> None:
    """LA régression à empêcher. `scores` tombe à zéro sous flash attention — et le poste entier
    tombait avec lui, donnant 205 Mo à 32k comme à 256k pendant que la mesure allait de 202 à 828.
    """
    petit = octets_tampons_calcul(_QWEN35B, 32768, 2048, flash_attention=True)
    grand = octets_tampons_calcul(_QWEN35B, 262144, 2048, flash_attention=True)
    assert grand > petit * 2


@pytest.mark.parametrize(("modele", "mesure_mio"), [(_QWEN35B, 60.72), (_QWEN9B, 48.16)])
def test_l_etat_recurrent_est_provisionne(modele: MetadonneesModele, mesure_mio: float) -> None:
    """Ce poste valait ZÉRO : les blocs hybrides étaient comptés comme s'ils ne coûtaient rien."""
    prevu_mio = octets_etat_recurrent(modele, modele.nombre_couches) / _MIO
    assert prevu_mio == pytest.approx(mesure_mio, abs=0.5)


def test_l_etat_recurrent_est_multiplie_par_le_nombre_de_slots() -> None:
    """llama-server ouvre quatre slots par défaut et alloue l'état pour CHACUN : 242,88 MiB mesurés
    contre 60,72 à un slot. `--parallel 1` est ce qui rend cette ligne théorique en production.
    """
    un = octets_etat_recurrent(_QWEN35B, 40, slots=1)
    quatre = octets_etat_recurrent(_QWEN35B, 40, slots=4)
    assert quatre == 4 * un
    assert quatre / _MIO == pytest.approx(242.88, abs=2.0)


def test_une_architecture_non_hybride_ne_paie_aucun_etat_recurrent() -> None:
    """Absence de clés `ssm.*` = poste nul, sans valeur inventée pour « faire quelque chose »."""
    dense = MetadonneesModele(
        taille_octets=6_000_000_000, nombre_couches=32, dimension_embedding=4096,
        nombre_tetes_attention=32, nombre_tetes_kv=8, dimension_tete=128,
        identifiant="dense", format="gguf", contexte_entrainement_max=32768,
        contexte_natif=32768, taille_vocabulaire=151936)
    assert octets_etat_recurrent(dense, 32) == 0
