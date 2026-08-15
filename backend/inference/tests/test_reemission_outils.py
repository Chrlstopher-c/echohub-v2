"""Preuve que les outils ne sont plus repassés au moteur après un tour ayant produit des résultats
(plan d'exécution, L10-b).

Défaut réel, observé il y a moins d'une heure : un modèle à qui on montrait une image a bouclé
trois fois sur l'outil de présentation au lieu de répondre. Cause identifiée : `outils` était
calculé une fois hors de la boucle de tours, puis repassé à `superviseur.generer` À CHAQUE tour, y
compris après qu'un tour a déjà exécuté un outil et reçu son résultat — le modèle voit donc
toujours les mêmes outils sous les yeux et n'a aucune raison d'arrêter d'en redemander.

Un vrai modèle est non déterministe : il ne boucle pas à tous les coups sur le même prompt, ce qui
rend une reproduction en conditions réelles peu fiable comme test de RÉGRESSION (elle reste dans
le rapport de mission, comme preuve ponctuelle). Ce test-ci matérialise le MÉCANISME plutôt que le
symptôme : `SuperviseurBoucleFactice` redemande l'outil **si et seulement si** on lui repasse des
outils non vides — exactement le déclencheur du bug. C'est `MoteurChat._flux` (le vrai) qui décide
quoi lui repasser à chaque tour, via `backend.outils.registre` (le vrai) pour l'exécution.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import backend.inference as domaine_inference
from backend.chat.modeles import ParametresEchantillonnage
from backend.chat.port_inference import MessageInference, RequeteGeneration
from backend.inference import MoteurChat
from backend.inference.engines_adapters.contrat import MessageChat, MorceauGeneration, OptionsGeneration
from backend.outils import registre
from backend.outils.contrat import ContexteExecution, DescriptionOutil, Outil

CONVERSATION_ATTENDUE = "conversation-boucle-42"


class SuperviseurBoucleFactice:
    """Redemande l'outil tant qu'on le lui présente — jamais autrement.

    Ce n'est pas « le modèle qui boucle » : c'est le harnais qui continue de lui montrer l'outil.
    Le simulateur rend cette dépendance explicite et vérifiable : sa seule variable d'entrée est
    `outils`, exactement celle que `MoteurChat._flux` doit cesser de repasser après un tour avec
    résultats.
    """

    def __init__(self) -> None:
        self.tours = 0
        self.outils_recus: list[bool] = []

    def generer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
        outils: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[MorceauGeneration]:
        self.tours += 1
        presents = bool(outils)
        self.outils_recus.append(presents)
        return self._flux(demande_outil=presents)

    async def _flux(self, *, demande_outil: bool) -> AsyncIterator[MorceauGeneration]:
        if demande_outil:
            yield MorceauGeneration(
                type="token",
                contenu='<tool_call>{"name": "outil_factice", "arguments": {}}</tool_call>',
            )
        else:
            yield MorceauGeneration(type="token", contenu="Réponse finale, sans nouvel outil.")


def _requete_test() -> RequeteGeneration:
    return RequeteGeneration(
        messages=[MessageInference(role="user", contenu="montre-moi le résultat")],
        parametres=ParametresEchantillonnage(),
        conversation_id=CONVERSATION_ATTENDUE,
    )


def _consommer(requete: RequeteGeneration) -> None:
    async def lire() -> None:
        moteur = MoteurChat()
        async for _ in moteur.generer(requete):
            pass

    asyncio.run(lire())


def test_les_outils_ne_sont_plus_repasses_apres_un_tour_avec_resultats(monkeypatch: Any) -> None:
    executions: list[int] = []

    async def executer_outil_factice(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
        executions.append(1)
        return "fait"

    outil_factice = Outil(
        description=DescriptionOutil(
            nom="outil_factice",
            description="Outil de test, sans effet réel.",
            parametres={"type": "object", "properties": {}},
        ),
        executer=executer_outil_factice,
    )
    monkeypatch.setitem(registre._OUTILS, outil_factice.nom, outil_factice)
    superviseur_factice = SuperviseurBoucleFactice()
    monkeypatch.setattr(domaine_inference, "superviseur", superviseur_factice)

    _consommer(_requete_test())

    # Le cœur de la preuve : un modèle qui redemanderait l'outil à chaque fois qu'on le lui montre
    # ne l'exécute qu'UNE fois si le harnais cesse de le lui montrer après le premier résultat.
    assert len(executions) == 1, "un seul appel d'outil exécuté : pas de boucle"
    assert superviseur_factice.tours == 2, "un tour avec l'outil visible, un tour de réponse sans"
    assert superviseur_factice.outils_recus == [True, False], (
        "les outils doivent être présents au premier tour et absents au second"
    )
