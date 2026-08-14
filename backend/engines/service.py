"""Façade du domaine `engines` — le seul point d'entrée des autres domaines.

Ce que le domaine promet :

- dire l'état réel de chaque moteur (installé, version, fonctionnel, architectures GPU), mesuré et
  non déduit ;
- installer une version de vLLM de façon annulable et ré-entrante ;
- fournir au domaine `inference` l'interpréteur d'une installation vLLM **validée**, ou refuser.

Ce que le domaine ne fait pas, volontairement : il ne compile pas llama.cpp (c'est le rôle du
build de l'image), il ne charge aucun modèle et ne démarre aucun serveur d'inférence (c'est le
domaine `inference`), et il ne mesure pas le matériel (c'est le domaine `system`).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from loguru import logger

from backend.core import InstallationMoteurEchouee
from backend.engines import llamacpp
from backend.engines import vllm as moteur_vllm
from backend.engines.modeles import (
    EtatMoteurs,
    EvenementInstallation,
    SanteMoteur,
    VersionVllm,
    maintenant_utc,
)


async def sante_llamacpp(*, forcer: bool = False) -> SanteMoteur:
    """État de santé de llama.cpp. `forcer` relance la sonde au lieu de rendre la dernière mesure."""
    return await llamacpp.sante(forcer=forcer)


async def versions_vllm(*, verifier: bool = False) -> list[VersionVllm]:
    """Versions de vLLM présentes. `verifier` relance une sonde dans chaque venv — coûteux."""
    if verifier:
        return await moteur_vllm.inventaire_verifie()
    return moteur_vllm.inventaire()


async def sante_vllm(*, verifier: bool = False) -> SanteMoteur:
    """État de santé agrégé du moteur vLLM."""
    return moteur_vllm.sante(await versions_vllm(verifier=verifier))


async def etat_des_moteurs(*, forcer_llamacpp: bool = False, verifier_vllm: bool = False) -> EtatMoteurs:
    """Vue complète du domaine, telle que l'écran Système la consomme."""
    versions = await versions_vllm(verifier=verifier_vllm)
    return EtatMoteurs(
        llamacpp=await sante_llamacpp(forcer=forcer_llamacpp),
        vllm=moteur_vllm.sante(versions),
        versions_vllm=versions,
        mesure_le=maintenant_utc(),
    )


def installer_vllm(
    version: str, *, remplacer: bool = False
) -> AsyncGenerator[EvenementInstallation, None]:
    """Installe une version de vLLM en diffusant sa progression.

    Le flux est la seule façon de suivre l'opération : elle dure des dizaines de minutes. Fermer
    le flux revient à annuler — le sous-processus est coupé et le venv partiel supprimé.

    Passe-plat délibéré, sans `async def` : envelopper le générateur casserait cette garantie
    d'annulation (cf. `vllm.installation.installer`).
    """
    return moteur_vllm.installer(version, remplacer=remplacer)


def annuler_installation_vllm(version: str) -> bool:
    """Interrompt l'installation en cours. Faux si aucune ne tourne pour cette version."""
    return moteur_vllm.annuler(version)


def supprimer_version_vllm(version: str) -> None:
    """Supprime définitivement un venv vLLM, sauf s'il est en cours d'installation."""
    nettoyee = moteur_vllm.valider_version(version)
    if nettoyee in moteur_vllm.installations_en_cours():
        raise InstallationMoteurEchouee(
            f"vLLM {nettoyee} est en cours d'installation : suppression refusée.",
            remediation="Annuler l'installation d'abord — elle nettoie elle-même son venv partiel.",
        )
    moteur_vllm.supprimer(nettoyee)
    logger.info("Version vLLM {} supprimée à la demande", nettoyee)


def python_vllm(version: str | None = None) -> Path:
    """Interpréteur d'une installation vLLM validée, pour le domaine `inference`.

    Lève `MoteurIndisponible` si aucune version utilisable n'existe. Un venv non validé n'est
    jamais rendu : c'est la garantie qui manquait à la v1, où le chargeur recevait un venv vide et
    échouait sur un `ModuleNotFoundError` sans explication.
    """
    return moteur_vllm.python_de_version(version)
