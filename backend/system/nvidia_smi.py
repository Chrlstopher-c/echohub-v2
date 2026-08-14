"""Mesure GPU via `nvidia-smi` — source de repli quand NVML est indisponible.

Le format de sortie de `nvidia-smi` n'est pas un contrat : champs absents selon la version du
pilote, `[N/A]` sur les métriques non supportées, colonnes en plus ou en moins. Le parsing est donc
défensif de bout en bout — un champ illisible vaut `None`, jamais une valeur de remplacement.

`compute_cap` n'existe pas sur les pilotes anciens et fait échouer la requête entière ; d'où une
seconde tentative sans ce champ plutôt qu'un abandon.
"""

from __future__ import annotations

import os
import subprocess

from loguru import logger

from backend.system.modeles import Gpu, PiloteNvidia, ReleveGpu, SourceMesureGpu

_MAX_GPUS = 16
_DELAI_MAX_S = 5.0
_MIO_EN_OCTETS = 1024 * 1024

# `nvidia-smi` rapporte les mémoires en MiB avec `nounits`.
_CHAMPS_COMPLETS = (
    "index",
    "name",
    "memory.total",
    "memory.free",
    "memory.used",
    "utilization.gpu",
    "temperature.gpu",
    "driver_version",
    "compute_cap",
)
_CHAMPS_REPLI = tuple(champ for champ in _CHAMPS_COMPLETS if champ != "compute_cap")

_VALEURS_ABSENTES = frozenset({"", "n/a", "[n/a]", "[not supported]", "not supported", "unknown"})

# Évite l'ouverture d'une console sur Windows natif ; sans effet ailleurs.
_DRAPEAUX = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _entier(brut: str | None) -> int | None:
    """Entier tolérant : `None` sur champ absent, non supporté ou non numérique."""
    if brut is None or brut.strip().lower() in _VALEURS_ABSENTES:
        return None
    try:
        return int(float(brut.strip()))
    except ValueError:
        logger.debug("Valeur nvidia-smi non numérique ignorée : {!r}", brut)
        return None


def _octets(brut: str | None) -> int | None:
    """Conversion MiB -> octets. `None` propagé si la mesure est absente."""
    mio = _entier(brut)
    return mio * _MIO_EN_OCTETS if mio is not None else None


def _capacite_calcul(brut: str | None) -> tuple[int | None, int | None]:
    """`compute_cap` arrive sous la forme `12.0`. Absent sur les pilotes anciens."""
    if brut is None or brut.strip().lower() in _VALEURS_ABSENTES:
        return None, None
    majeur, _, mineur = brut.strip().partition(".")
    if not majeur.isdigit():
        return None, None
    return int(majeur), int(mineur) if mineur.isdigit() else 0


def _interroger(champs: tuple[str, ...]) -> str | None:
    """Exécute `nvidia-smi` pour un jeu de champs. `None` sur binaire absent, timeout ou échec."""
    commande = ["nvidia-smi", f"--query-gpu={','.join(champs)}", "--format=csv,noheader,nounits"]
    try:
        resultat = subprocess.run(
            commande,
            capture_output=True,
            text=True,
            timeout=_DELAI_MAX_S,
            check=False,
            creationflags=_DRAPEAUX,
        )
    except FileNotFoundError:
        logger.debug("nvidia-smi introuvable dans le PATH.")
        return None
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("Appel nvidia-smi échoué : {}", exc)
        return None

    if resultat.returncode != 0:
        logger.debug("nvidia-smi a répondu {} : {}", resultat.returncode, resultat.stderr.strip())
        return None
    return resultat.stdout.strip() or None


def _construire_gpu(valeurs: dict[str, str]) -> Gpu | None:
    """Un GPU dont la VRAM totale est illisible n'est pas exploitable : on l'écarte."""
    totale = _octets(valeurs.get("memory.total"))
    libre = _octets(valeurs.get("memory.free"))
    if totale is None or libre is None:
        logger.warning("GPU écarté, mémoire illisible dans la sortie nvidia-smi : {}", valeurs)
        return None

    utilisee = _octets(valeurs.get("memory.used"))
    majeur, mineur = _capacite_calcul(valeurs.get("compute_cap"))
    return Gpu(
        index=_entier(valeurs.get("index")) or 0,
        nom=(valeurs.get("name") or "GPU NVIDIA").strip(),
        compute_majeur=majeur,
        compute_mineur=mineur,
        vram_totale_octets=totale,
        vram_libre_octets=libre,
        vram_utilisee_octets=utilisee if utilisee is not None else max(0, totale - libre),
        utilisation_pct=_entier(valeurs.get("utilization.gpu")),
        temperature_c=_entier(valeurs.get("temperature.gpu")),
    )


def _decouper(ligne: str, champs: tuple[str, ...]) -> dict[str, str] | None:
    """Associe chaque colonne à son champ. Une ligne trop courte est ignorée, pas complétée."""
    colonnes = [colonne.strip() for colonne in ligne.split(",")]
    if len(colonnes) < len(champs):
        logger.warning("Ligne nvidia-smi incomplète, ignorée : {!r}", ligne)
        return None
    return dict(zip(champs, colonnes))


def _construire_pilote(lignes: list[dict[str, str]]) -> PiloteNvidia | None:
    """La version du pilote est répétée sur chaque ligne : la première lisible suffit."""
    for valeurs in lignes:
        version = (valeurs.get("driver_version") or "").strip()
        if version.lower() not in _VALEURS_ABSENTES:
            return PiloteNvidia(version=version)
    return None


def _parser_sortie(sortie: str, champs: tuple[str, ...]) -> ReleveGpu | None:
    """Convertit la sortie CSV en relevé. `None` si aucune ligne n'a produit de GPU exploitable."""
    decoupees = [_decouper(ligne, champs) for ligne in sortie.splitlines()[:_MAX_GPUS]]
    lignes = [valeurs for valeurs in decoupees if valeurs is not None]
    construits = [_construire_gpu(valeurs) for valeurs in lignes]
    gpus = [gpu for gpu in construits if gpu is not None]
    if not gpus:
        return None
    return ReleveGpu(source=SourceMesureGpu.NVIDIA_SMI, pilote=_construire_pilote(lignes), gpus=gpus)


def lire_via_nvidia_smi() -> ReleveGpu | None:
    """Relevé GPU via `nvidia-smi`, ou `None` si aucun GPU n'a pu être lu.

    Deux tentatives au plus : jeu de champs complet, puis jeu réduit sans `compute_cap` pour les
    pilotes qui ne connaissent pas ce champ et rejettent alors la requête entière.
    """
    for champs in (_CHAMPS_COMPLETS, _CHAMPS_REPLI):
        sortie = _interroger(champs)
        if sortie is None:
            continue
        releve = _parser_sortie(sortie, champs)
        if releve is not None:
            return releve
    return None
