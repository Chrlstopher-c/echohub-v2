"""Preuve que l'identité de la conversation atteint l'exécution d'un outil (plan d'exécution, 2.5).

Chaîne exercée réellement, sans mock à mi-chemin : `MoteurChat.generer` (le vrai) est appelé avec
une `RequeteGeneration` réelle ; seul le LLM sous-jacent est remplacé (`superviseur`), parce que
c'est la seule frontière qui exige un GPU. Le tour simulé demande l'outil factice enregistré ici,
et le registre RÉEL (`backend.outils.registre`) l'exécute — c'est donc `MoteurChat._flux` qui doit
avoir construit et transmis le `ContexteExecution`, pas un raccourci du test.

Les coroutines sont pilotées par `asyncio.run`, comme dans `chat/tests/test_flux_branche.py` : le
dépôt ne configure `asyncio_mode` nulle part.
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

CONVERSATION_ATTENDUE = "conversation-attendue-42"


class SuperviseurFactice:
    """Simule le modèle chargé : demande l'outil factice au premier tour, répond en clair ensuite.

    Se substitue à `backend.inference.superviseur` — la seule chose que ce test ne peut pas faire
    tourner réellement est un GGUF sur GPU. Tout le reste (`MoteurChat`, le registre, l'outil) est
    le code de production, inchangé.
    """

    def __init__(self) -> None:
        self.tours = 0

    def generer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
        outils: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[MorceauGeneration]:
        self.tours += 1
        return self._flux(premier_tour=self.tours == 1)

    async def _flux(self, *, premier_tour: bool) -> AsyncIterator[MorceauGeneration]:
        if premier_tour:
            yield MorceauGeneration(
                type="token",
                contenu='<tool_call>{"name": "outil_factice", "arguments": {}}</tool_call>',
            )
        else:
            yield MorceauGeneration(type="token", contenu="Réponse finale, sans nouvel outil.")


def _requete_test() -> RequeteGeneration:
    return RequeteGeneration(
        messages=[MessageInference(role="user", contenu="bonjour")],
        parametres=ParametresEchantillonnage(),
        conversation_id=CONVERSATION_ATTENDUE,
    )


def _consommer(requete: RequeteGeneration) -> None:
    async def lire() -> None:
        moteur = MoteurChat()
        async for _ in moteur.generer(requete):
            pass

    asyncio.run(lire())


def test_loutil_recoit_lidentifiant_de_la_conversation_attendue(monkeypatch: Any) -> None:
    contextes_recus: list[ContexteExecution] = []

    async def executer_outil_factice(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
        contextes_recus.append(contexte)
        return "fait"

    outil_factice = Outil(
        description=DescriptionOutil(
            nom="outil_factice",
            description="Outil de test, sans effet réel.",
            parametres={"type": "object", "properties": {}},
        ),
        executer=executer_outil_factice,
    )
    # Enregistrement direct dans le registre RÉEL : c'est lui qui doit relayer le contexte reçu
    # de `MoteurChat`, exactement comme il le ferait pour un outil de production.
    monkeypatch.setitem(registre._OUTILS, outil_factice.nom, outil_factice)
    monkeypatch.setattr(domaine_inference, "superviseur", SuperviseurFactice())

    _consommer(_requete_test())

    assert len(contextes_recus) == 1, "l'outil factice doit avoir été exécuté exactement une fois"
    assert contextes_recus[0].conversation_id == CONVERSATION_ATTENDUE
    # Le bac est désormais le dossier de la conversation dans le workspace partagé avec l'atelier :
    # son dernier segment est l'identifiant de la conversation (c'est lui qui voyage vers l'atelier
    # comme `sous_dossier`), et il vit sous la racine `atelier_workspace`.
    from backend.core import get_settings

    assert contextes_recus[0].racine_bac.name == CONVERSATION_ATTENDUE
    assert contextes_recus[0].racine_bac.parent == get_settings().atelier_workspace
