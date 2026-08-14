"""Interface commune des adaptateurs de moteurs.

Quatre opérations, pas une de plus : charger un plan, décharger, générer, sonder. Tout ce qui
dépasse (choix du moteur, dimensionnement, dégradation après échec) appartient au planificateur ou
au superviseur — un adaptateur applique, il ne décide pas.

Le superviseur ne connaît que ce contrat : ajouter un moteur consiste à écrire une classe ici, sans
toucher ni l'API ni le planificateur.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator, ClassVar, Sequence

from backend.inference.engines_adapters.contrat import (
    CauseEchec,
    EtatMoteur,
    MessageChat,
    MorceauGeneration,
    MoteurSupporte,
    OptionsGeneration,
    PlanChargement,
    Sante,
)
from backend.inference.engines_adapters.diagnostic import Diagnostic, EchecChargement, preverifier_source
from backend.inference.engines_adapters.journal import SessionChargement


class AdaptateurMoteur(ABC):
    """Pilote d'un moteur d'inférence, pour un seul modèle à la fois."""

    moteur: ClassVar[MoteurSupporte]

    @abstractmethod
    async def charger(self, plan: PlanChargement, session: SessionChargement | None = None) -> EtatMoteur:
        """Applique le plan et rend l'état servi. Lève `EchecChargement` avec une cause qualifiée."""

    @abstractmethod
    async def decharger(self) -> None:
        """Libère le moteur. Idempotent : décharger un moteur déjà vide n'est pas une erreur."""

    @abstractmethod
    def generer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
    ) -> AsyncIterator[MorceauGeneration]:
        """Flux de tokens du modèle chargé. Se termine toujours par un morceau `fin`."""

    @abstractmethod
    async def sante(self) -> Sante:
        """Sonde le moteur maintenant, sans se fier à l'état mémorisé au chargement."""

    @property
    @abstractmethod
    def etat(self) -> EtatMoteur | None:
        """Dernier état servi, ou None si rien n'est chargé."""


def exiger_moteur(plan: PlanChargement, attendu: MoteurSupporte) -> None:
    """Refuse un plan destiné à un autre moteur — erreur de routage, pas erreur de modèle."""
    if plan.moteur is not attendu:
        raise EchecChargement(
            Diagnostic(
                cause=CauseEchec.PLAN_INCOMPLET,
                message=f"Plan destiné au moteur {plan.moteur.value}, reçu par l'adaptateur {attendu.value}.",
                remediation="Corriger le routage du plan : le moteur est choisi par le planificateur.",
            )
        )


def exiger_source_lisible(plan: PlanChargement) -> Path:
    """Contrôle la source avant tout démarrage de moteur, et rend le chemin résolu.

    Ce contrôle est la condition qui permet ensuite de disculper le fichier : un échec postérieur
    portant un message générique ne peut plus lui être imputé.
    """
    chemin = Path(plan.chemin_modele)
    diagnostic = preverifier_source(chemin, plan.moteur)
    if diagnostic is not None:
        raise EchecChargement(diagnostic)
    return chemin
