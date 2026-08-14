"""Qualification des échecs de chargement : nommer la cause réelle, jamais accuser le fichier.

Défaut central de la v1, payé en heures : tout échec remontait « Failed to load model from file ».
Ce message est celui que llama.cpp émet en dernier ressort, y compris quand le fichier est
parfaitement lisible et que la vraie cause est ailleurs — VRAM saturée, moteur compilé sans CUDA,
contexte trop grand pour le cache KV. L'utilisateur retéléchargeait alors un fichier sain.

Règle appliquée ici : le fichier n'est déclaré coupable que si sa lecture a été *vérifiée* fautive
(absent, illisible, magie GGUF invalide, taille nulle). Sinon, un message générique dégrade vers
`INDETERMINEE` en portant l'extrait de journal du moteur — un aveu d'ignorance exploitable vaut
mieux qu'une accusation fausse.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Pattern

from loguru import logger
from pydantic import BaseModel, Field

from backend.core import ChargementEchoue
from backend.inference.engines_adapters.contrat import CauseEchec, MoteurSupporte

# Longueur d'extrait de journal conservée : assez pour lire la pile d'erreur du moteur, assez peu
# pour rester affichable dans l'interface sans la noyer.
LONGUEUR_EXTRAIT = 1200

_MAGIE_GGUF = b"GGUF"

_STATUT_PAR_CAUSE: dict[CauseEchec, int] = {
    CauseEchec.VRAM_INSUFFISANTE: 507,
    CauseEchec.VRAM_NON_LIBEREE: 507,
    CauseEchec.RAM_INSUFFISANTE: 507,
    CauseEchec.CONTEXTE_TROP_GRAND: 507,
    CauseEchec.MOTEUR_ABSENT: 503,
    CauseEchec.MOTEUR_SANS_CUDA: 503,
    CauseEchec.FICHIER_ILLISIBLE: 422,
    CauseEchec.ARCHITECTURE_INCONNUE: 422,
    CauseEchec.QUANTIFICATION_INCOMPATIBLE: 422,
    CauseEchec.PLAN_INCOMPLET: 422,
    CauseEchec.DELAI_DEPASSE: 504,
    CauseEchec.ANNULE: 409,
    CauseEchec.INDETERMINEE: 500,
}


class Diagnostic(BaseModel):
    """Cause qualifiée d'un échec, avec de quoi agir et de quoi replanifier."""

    cause: CauseEchec
    message: str
    remediation: str = ""
    indices: dict[str, Any] = Field(default_factory=dict)


class EchecChargement(ChargementEchoue):
    """Échec de chargement porteur de son diagnostic. Seule exception levée par les adaptateurs."""

    def __init__(self, diagnostic: Diagnostic, *, details: dict[str, Any] | None = None) -> None:
        complements: dict[str, Any] = {"cause": diagnostic.cause.value, **diagnostic.indices}
        complements.update(details or {})
        super().__init__(diagnostic.message, remediation=diagnostic.remediation, details=complements)
        self.diagnostic = diagnostic
        self.code = f"chargement_{diagnostic.cause.value}"
        # Attribut d'instance : masque le 500 de la classe pour que l'API réponde le bon statut.
        self.statut_http = _STATUT_PAR_CAUSE.get(diagnostic.cause, 500)


# (motif, cause, message, remédiation) — ordonné du plus spécifique au plus générique.
_SIGNATURES: tuple[tuple[Pattern[str], CauseEchec, str, str], ...] = (
    (
        re.compile(r"is less than desired GPU memory utilization|free memory on device", re.I),
        CauseEchec.VRAM_INSUFFISANTE,
        "La VRAM libre est inférieure à la fraction demandée par le plan.",
        "Décharger le modèle en cours, ou replanifier avec une fraction de VRAM plus basse.",
    ),
    (
        re.compile(r"out of memory|cudamalloc|cuda error: out of memory|failed to allocate", re.I),
        CauseEchec.VRAM_INSUFFISANTE,
        "Le GPU a refusé une allocation : la VRAM demandée dépasse la VRAM réellement libre.",
        "Replanifier avec moins de couches GPU ou un contexte plus court.",
    ),
    (
        re.compile(r"max seq len|kv cache|estimated maximum model length|larger than the maximum", re.I),
        CauseEchec.CONTEXTE_TROP_GRAND,
        "Le cache KV du contexte demandé ne tient pas dans la mémoire restante.",
        "Replanifier avec un contexte plus court, ou un cache KV quantifié.",
    ),
    (
        re.compile(r"cannot allocate memory|std::bad_alloc|killed process|oom-killer", re.I),
        CauseEchec.RAM_INSUFFISANTE,
        "La RAM système manque pour l'offload CPU prévu par le plan.",
        "Sous WSL2, relever la limite mémoire dans .wslconfig, ou réduire les couches hors GPU.",
    ),
    (
        re.compile(r"unknown model architecture|unsupported model architecture|unknown architecture", re.I),
        CauseEchec.ARCHITECTURE_INCONNUE,
        "L'architecture déclarée par le modèle est inconnue de cette version du moteur.",
        "Mettre à jour le moteur depuis l'écran Système, ou choisir un autre format du modèle.",
    ),
    (
        re.compile(r"not supported by (vllm|llama)|architecture .* is not supported|no supported model", re.I),
        CauseEchec.ARCHITECTURE_INCONNUE,
        "Le moteur ne sait pas servir cette architecture de modèle.",
        "Utiliser l'autre moteur, ou une version du modèle dans un format pris en charge.",
    ),
    (
        re.compile(r"not aligned with the quantized weight shape|awq|gptq .* unsupported", re.I),
        CauseEchec.QUANTIFICATION_INCOMPATIBLE,
        "La quantification du modèle est incompatible avec cette architecture dans ce moteur.",
        "Prendre une variante GGUF du modèle, ou une quantification prise en charge par le moteur.",
    ),
    (
        re.compile(r"no cuda-capable device|no cuda devices|cuda driver version|libcuda\.so.*not found", re.I),
        CauseEchec.MOTEUR_SANS_CUDA,
        "Le moteur ne voit aucun GPU CUDA utilisable.",
        "Vérifier le pilote hôte (≥ 570 pour les RTX 50xx) et l'exposition du GPU au conteneur.",
    ),
    (
        re.compile(r"ggml_cuda|cuda backend .* not (available|enabled)|built without cuda", re.I),
        CauseEchec.MOTEUR_SANS_CUDA,
        "Le moteur installé n'a pas de support CUDA compilé.",
        "Réinstaller llama-cpp-python depuis les sources (--no-binary) : le wheel PyPI est CPU-only.",
    ),
    (
        re.compile(r"no module named|modulenotfounderror|command not found|is not recognized", re.I),
        CauseEchec.MOTEUR_ABSENT,
        "Le moteur demandé n'est pas installé dans l'environnement attendu.",
        "Installer le moteur depuis l'écran Système avant de charger un modèle.",
    ),
    (
        re.compile(r"no such file or directory|permission denied|invalid magic|unexpected end of file"
                   r"|tensor .* not found|is not a directory|truncated", re.I),
        CauseEchec.FICHIER_ILLISIBLE,
        "Le fichier de modèle est absent, illisible ou incomplet.",
        "Relancer le téléchargement du modèle : l'artefact local est inexploitable.",
    ),
)

# Message de dernier ressort de llama.cpp : ne prouve rien sur le fichier lui-même.
_GENERIQUE_LLAMA = re.compile(r"failed to load model( from file)?|llama_(load_model|model_load)", re.I)

_LIGNES_INTERESSANTES = ("Error:", "error:", "ERROR", "Traceback", "assert", "CUDA", "failed")


def extrait_journal(texte: str, longueur: int = LONGUEUR_EXTRAIT) -> str:
    """Fin du journal moteur : c'est là que se trouve la cause, pas dans son démarrage."""
    nettoye = (texte or "").strip()
    return nettoye[-longueur:] if len(nettoye) > longueur else nettoye


def derniere_ligne_significative(texte: str) -> str:
    """Dernière ligne portant une marque d'erreur, utilisée comme résumé lisible."""
    lignes: Iterable[str] = reversed((texte or "").splitlines())
    for ligne in lignes:
        if any(marque in ligne for marque in _LIGNES_INTERESSANTES):
            return ligne.strip()[:300]
    return ""


def contexte_suggere(texte: str) -> int | None:
    """Contexte maximal suggéré par vLLM dans son propre message d'échec, s'il en propose un."""
    trouve = re.search(r"estimated maximum model length is (\d+)", texte or "", re.I)
    if not trouve:
        return None
    try:
        return int(trouve.group(1))
    except ValueError:  # groupe numérique non convertible : le format du message a changé
        logger.warning("Contexte suggéré illisible dans le journal du moteur")
        return None


def _indices(corpus: str) -> dict[str, Any]:
    """Éléments joints à tout diagnostic : extrait de journal, résumé, et suggestion du moteur."""
    releves: dict[str, Any] = {
        "extrait": extrait_journal(corpus),
        "resume": derniere_ligne_significative(corpus),
    }
    suggestion = contexte_suggere(corpus)
    if suggestion is not None:
        releves["contexte_suggere"] = suggestion
    return releves


def qualifier(texte: str, *, source_verifiee: bool = False, exception: BaseException | None = None) -> Diagnostic:
    """Nomme la cause d'un échec à partir du journal du moteur et, si fournie, de l'exception.

    `source_verifiee` : True quand le fichier ou le répertoire du modèle a déjà été contrôlé lisible.
    Dans ce cas un message générique ne peut plus être imputé au fichier.
    """
    corpus = "\n".join(part for part in (texte or "", repr(exception) if exception else "") if part)
    indices = _indices(corpus)

    for motif, cause, message, remediation in _SIGNATURES:
        if not motif.search(corpus):
            continue
        if cause is CauseEchec.FICHIER_ILLISIBLE and source_verifiee:
            continue  # lecture déjà contrôlée : ne pas ré-accuser le fichier sur un motif ambigu
        return Diagnostic(cause=cause, message=message, remediation=remediation, indices=indices)

    if _GENERIQUE_LLAMA.search(corpus) and not source_verifiee:
        return Diagnostic(
            cause=CauseEchec.FICHIER_ILLISIBLE,
            message="Le moteur n'a pas pu ouvrir le fichier de modèle.",
            remediation="Vérifier le chemin, puis relancer le téléchargement du modèle.",
            indices=indices,
        )

    return Diagnostic(
        cause=CauseEchec.INDETERMINEE,
        message=(
            "Le moteur a échoué sans cause identifiable. Le fichier de modèle a été contrôlé lisible : "
            "la cause est ailleurs, voir l'extrait du journal moteur."
            if source_verifiee
            else "Le moteur a échoué sans cause identifiable, voir l'extrait du journal moteur."
        ),
        remediation="Joindre l'extrait au rapport : cet échec n'a pas encore de signature connue.",
        indices=indices,
    )


def _diagnostic_fichier(message: str, chemin: Path, remediation: str) -> Diagnostic:
    return Diagnostic(
        cause=CauseEchec.FICHIER_ILLISIBLE,
        message=message,
        remediation=remediation,
        indices={"chemin": str(chemin)},
    )


def preverifier_source(chemin: Path, moteur: MoteurSupporte) -> Diagnostic | None:
    """Contrôle la lisibilité réelle de la source AVANT de démarrer le moteur.

    C'est ce contrôle qui autorise, plus tard, à disculper le fichier : sans lui, la qualification
    d'un message générique resterait une supposition.
    """
    try:
        if not chemin.exists():
            return _diagnostic_fichier("Le chemin du modèle n'existe pas.", chemin, "Vérifier le registre local.")
        if moteur is MoteurSupporte.VLLM and chemin.is_dir():
            return _verifier_repertoire_vllm(chemin)
        if not chemin.is_file():
            return _diagnostic_fichier("Le chemin du modèle n'est pas un fichier.", chemin, "Corriger le chemin.")
        if chemin.stat().st_size == 0:
            return _diagnostic_fichier("Le fichier de modèle est vide.", chemin, "Relancer le téléchargement.")
        with chemin.open("rb") as flux:
            entete = flux.read(4)
    except OSError as exc:
        logger.error("Pré-vérification du modèle {} impossible : {}", chemin, exc)
        return _diagnostic_fichier(
            f"Le fichier de modèle est illisible : {exc}", chemin, "Vérifier les droits et le montage du volume."
        )

    if chemin.suffix.lower() == ".gguf" and entete != _MAGIE_GGUF:
        return _diagnostic_fichier(
            "L'en-tête du fichier n'est pas celui d'un GGUF : téléchargement tronqué ou fichier LFS non résolu.",
            chemin,
            "Relancer le téléchargement du modèle.",
        )
    return None


def _verifier_repertoire_vllm(chemin: Path) -> Diagnostic | None:
    """Un dépôt servi par vLLM doit au minimum exposer sa configuration de modèle."""
    if not (chemin / "config.json").exists():
        return _diagnostic_fichier(
            "Le répertoire du modèle ne contient pas de config.json : dépôt incomplet.",
            chemin,
            "Relancer le téléchargement du dépôt complet.",
        )
    return None
