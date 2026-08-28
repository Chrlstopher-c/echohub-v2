"""L'annulation d'un chargement doit décharger l'adaptateur — sinon un sous-processus déjà lancé
reste référencé sans que personne ne le récolte.

Mesuré le 2026-08-28 : `llama-server` (PID 337338, PPID le backend) zombie depuis plusieurs heures.
`_demarrer` lance le processus puis attend sa santé ; une annulation pendant cette attente traverse
`adaptateur.charger()` sans jamais atteindre le `poll()` qui aurait récolté le processus mort — ni
au démarrage suivant, puisque rien ne relance de chargement tant que l'utilisateur ne le redemande
pas. `SuperviseurInference._executer` est le seul point qui voit passer CETTE exception pour tous
les moteurs : c'est là que le nettoyage doit vivre, pas dans chaque adaptateur.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.inference.engines_adapters.contrat import (
    EtatChargement,
    EtatMoteur,
    MoteurSupporte,
    PlanChargement,
    Sante,
)
from backend.inference.engines_adapters.superviseur import SuperviseurInference


class AdaptateurBloquant:
    """Adaptateur factice : `charger` bloque indéfiniment, `decharger` note qu'on l'a appelé."""

    moteur = MoteurSupporte.LLAMA_CPP

    def __init__(self) -> None:
        self.decharge_appele = False
        self.entre_dans_charger = asyncio.Event()
        self._etat: EtatMoteur | None = None

    @property
    def etat(self) -> EtatMoteur | None:
        return self._etat

    async def charger(self, plan: PlanChargement, session: object = None) -> EtatMoteur:
        self.entre_dans_charger.set()
        await asyncio.Event().wait()  # ne se termine jamais tant que la tâche n'est pas annulée
        raise AssertionError("inatteignable : l'attente ci-dessus ne rend jamais la main")

    async def decharger(self) -> None:
        self.decharge_appele = True

    async def sante(self) -> Sante:
        return Sante(disponible=False)

    def generer(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError


def _plan() -> PlanChargement:
    return PlanChargement(
        moteur=MoteurSupporte.LLAMA_CPP,
        chemin_modele="/tmp/modele-inexistant.gguf",
        identifiant_modele="test/annulation::modele.gguf",
        couches_gpu=0,
        contexte=2048,
        batch=512,
    )


def test_annulation_pendant_charger_decharge_ladaptateur() -> None:
    """Sans le correctif, `decharger()` n'est jamais appelé et le processus lancé reste orphelin."""
    superviseur = SuperviseurInference()
    adaptateur = AdaptateurBloquant()
    superviseur._adaptateurs[MoteurSupporte.LLAMA_CPP] = adaptateur

    async def scenario() -> None:
        await superviseur.demarrer_chargement(_plan())
        await asyncio.wait_for(adaptateur.entre_dans_charger.wait(), timeout=1.0)
        await superviseur._annuler_tache()

    asyncio.run(scenario())

    assert adaptateur.decharge_appele is True
    assert superviseur.statut().etat is EtatChargement.ECHOUE


def test_chargement_qui_reussit_ne_declenche_pas_de_decharge_superflu() -> None:
    """Le nettoyage d'annulation ne doit pas s'activer sur un chargement qui aboutit normalement."""

    class AdaptateurImmediat(AdaptateurBloquant):
        async def charger(self, plan: PlanChargement, session: object = None) -> EtatMoteur:
            self._etat = EtatMoteur(
                moteur=MoteurSupporte.LLAMA_CPP, modele=plan.nom_affiche, pret=True,
                contexte=plan.contexte, couches_gpu=plan.couches_gpu,
            )
            return self._etat

    superviseur = SuperviseurInference()
    adaptateur = AdaptateurImmediat()
    superviseur._adaptateurs[MoteurSupporte.LLAMA_CPP] = adaptateur

    asyncio.run(superviseur.demarrer_chargement(_plan()))
    asyncio.run(superviseur.attendre(1.0))

    assert adaptateur.decharge_appele is False
    assert superviseur.statut().etat is EtatChargement.PRET


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
