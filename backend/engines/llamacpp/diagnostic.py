"""État de santé de llama.cpp — vérification, jamais compilation.

Le binaire `llama-cpp-python` est recompilé avec le support CUDA au moment du build de l'image
(cf. Dockerfile et COMPATIBILITE-GPU.md). Ce module n'a donc qu'un rôle : dire si ce qui a été
compilé est bien là, et conforme à ce qui était attendu. Il ne recompile rien à l'exécution — une
compilation dans un conteneur en cours de service prendrait des dizaines de minutes et laisserait
le moteur dans un état indéterminé pendant tout ce temps.

Ce qui est vérifié, et pourquoi :
- l'import passe (le paquet est présent, la bibliothèque native se charge) ;
- le binaire expose des architectures CUDA (`ARCHS`) — un wheel PyPI standard n'en expose aucune,
  il est CPU-only, et l'application « marche » sans jamais toucher le GPU ;
- `FORCE_CUBLAS` vaut 1 — c'est la trace du contournement du segfault de nvcc 12.8 sur les kernels
  MMQ pour `compute_120a`. Son absence signale un binaire construit autrement que prévu.

Choix assumé : un binaire dont les architectures ne couvrent pas tout le parc reste FONCTIONNEL,
avec une non-conformité signalée explicitement. Ce domaine ne sait pas quel GPU est présent —
c'est le domaine `system` qui le mesure — donc il ne peut pas déclarer défaillant ce qui est
peut-être parfaitement adapté à la machine locale.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from backend.engines._sonde import interroger
from backend.engines.modeles import (
    ARCHITECTURES_PARC,
    DiagnosticLlamaCpp,
    SanteMoteur,
    StatutMoteur,
    maintenant_utc,
)

# Le binaire est figé dans l'image : il ne peut pas changer pendant la vie du process. Le cache
# évite de relancer un chargement de bibliothèque native à chaque affichage de l'écran Système.
DUREE_CACHE_S = 600.0

# L'import de `llama_cpp` charge la bibliothèque CUDA : quelques secondes à froid, davantage sur
# un premier accès disque lent. Au-delà, quelque chose est bloqué et il vaut mieux le dire.
TIMEOUT_SONDE_S = 90.0

_SCRIPT_SONDE = Path(__file__).with_name("sonde.py")


@dataclass
class _CacheDiagnostic:
    """Mémoire du dernier diagnostic. État partagé explicite, confiné à ce module."""

    valeur: DiagnosticLlamaCpp | None = field(default=None)
    mesure_a: float = field(default=0.0)

    def valide(self) -> bool:
        return self.valeur is not None and (time.monotonic() - self.mesure_a) < DUREE_CACHE_S

    def deposer(self, valeur: DiagnosticLlamaCpp) -> None:
        self.valeur = valeur
        self.mesure_a = time.monotonic()


_CACHE = _CacheDiagnostic()


async def diagnostiquer(*, forcer: bool = False) -> DiagnosticLlamaCpp:
    """Lance la sonde (ou rend la dernière mesure) et retourne le constat brut."""
    if not forcer and _CACHE.valide() and _CACHE.valeur is not None:
        return _CACHE.valeur

    charge = await interroger(Path(sys.executable), _SCRIPT_SONDE, timeout_s=TIMEOUT_SONDE_S)
    if charge.donnees is None:
        diagnostic = DiagnosticLlamaCpp(
            importable=False,
            erreur=charge.sortie_brute[-500:] or "La sonde n'a produit aucun résultat.",
            type_erreur="SondeExpiree" if charge.expire else "SondeSansReponse",
        )
    else:
        diagnostic = DiagnosticLlamaCpp.model_validate(charge.donnees)

    _CACHE.deposer(diagnostic)
    logger.info(
        "llama.cpp : importable={} archs={} force_cublas={}",
        diagnostic.importable,
        diagnostic.architectures_gpu,
        diagnostic.force_cublas,
    )
    return diagnostic


def _details(diagnostic: DiagnosticLlamaCpp) -> dict[str, str]:
    return {
        "force_cublas": _texte(diagnostic.force_cublas),
        "offload_gpu": _texte(diagnostic.offload_gpu),
        "architectures_attendues": ",".join(ARCHITECTURES_PARC),
        "conforme_au_build_attendu": _texte(_conforme(diagnostic)),
        "info_systeme": diagnostic.info_systeme,
    }


def _texte(valeur: bool | None) -> str:
    return "inconnu" if valeur is None else ("oui" if valeur else "non")


def _conforme(diagnostic: DiagnosticLlamaCpp) -> bool:
    """Conformité au build décrit dans COMPATIBILITE-GPU.md : ARCHS = 860,1200 et FORCE_CUBLAS = 1."""
    couvre = all(arch in diagnostic.architectures_gpu for arch in ARCHITECTURES_PARC)
    return couvre and diagnostic.force_cublas is True


def _statut(diagnostic: DiagnosticLlamaCpp) -> tuple[StatutMoteur, str, str]:
    """Traduit le constat en statut, diagnostic lisible et remédiation."""
    if not diagnostic.importable:
        if diagnostic.type_erreur == "ModuleNotFoundError":
            return (
                StatutMoteur.ABSENT,
                "llama-cpp-python n'est pas installé dans l'environnement du backend.",
                "Reconstruire l'image : l'installation de llama-cpp-python fait partie du Dockerfile.",
            )
        return (
            StatutMoteur.DEFAILLANT,
            f"Le chargement de la bibliothèque native échoue ({diagnostic.type_erreur}) : {diagnostic.erreur}",
            "Reconstruire l'image et vérifier le pilote NVIDIA hôte (≥ 570 pour les RTX 50xx).",
        )
    if not diagnostic.architectures_gpu:
        return (
            StatutMoteur.DEFAILLANT,
            "Le binaire n'expose aucune architecture CUDA : c'est le wheel PyPI, compilé CPU-only.",
            "Reconstruire l'image : l'étape `pip install --no-binary llama-cpp-python` a été contournée.",
        )
    if diagnostic.offload_gpu is False:
        return (
            StatutMoteur.DEFAILLANT,
            "Le binaire déclare ne pas supporter l'offload GPU malgré des architectures CUDA compilées.",
            "Reconstruire l'image depuis une base `nvidia/cuda:12.8.0-devel` et vérifier CMAKE_ARGS.",
        )
    return StatutMoteur.FONCTIONNEL, _message_conformite(diagnostic), ""


def _message_conformite(diagnostic: DiagnosticLlamaCpp) -> str:
    architectures = ", ".join(diagnostic.architectures_gpu)
    if _conforme(diagnostic):
        return f"Binaire CUDA conforme au build attendu ({architectures}, FORCE_CUBLAS actif)."
    manquantes = [arch for arch in ARCHITECTURES_PARC if arch not in diagnostic.architectures_gpu]
    ecarts = []
    if manquantes:
        ecarts.append(f"architectures manquantes : {', '.join(manquantes)}")
    if diagnostic.force_cublas is not True:
        ecarts.append("FORCE_CUBLAS inactif (contournement du segfault nvcc 12.8 absent)")
    return f"Binaire CUDA opérationnel ({architectures}) mais écarté du build attendu — {' ; '.join(ecarts)}."


async def sante(*, forcer: bool = False) -> SanteMoteur:
    """État de santé de llama.cpp, tel qu'exposé hors du domaine."""
    diagnostic = await diagnostiquer(forcer=forcer)
    statut, message, remediation = _statut(diagnostic)
    return SanteMoteur(
        moteur="llamacpp",
        statut=statut,
        version=diagnostic.version,
        architectures_gpu=diagnostic.architectures_gpu,
        diagnostic=message,
        remediation=remediation,
        details=_details(diagnostic),
        mesure_le=maintenant_utc(),
    )
