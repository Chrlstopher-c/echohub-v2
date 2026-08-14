"""Routes HTTP du domaine `chat`.

Le routeur ne porte pas le préfixe `/api` : la couche d'assemblage (`main.py`) le monte, comme pour
les autres domaines, ce qui laisse un seul endroit décider de la forme des URL publiques.

Toutes les routes sont `async`. Les accès SQLite qu'elles font sont synchrones, mais ce sont des
lectures indexées sur un fichier local : leur coût est sans commune mesure avec la génération
elle-même, et les exécuter dans un pool de threads multiplierait les connexions SQLite (une par
thread) pour rien.

Traduction des erreurs : un décorateur unique transforme toute `EchoHubError` en réponse HTTP en
s'appuyant sur `statut_http` et `to_dict()`. Aucune table de correspondance n'est réécrite ici —
c'était la promesse de `core.errors`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger

from backend.chat import annulation, depot, flux_sse, generation
from backend.chat.modeles import (
    ConversationDetaillee,
    CreationConversation,
    DemandeGeneration,
    MajConversation,
    MajReglages,
    MessageChat,
    ReglagesConversation,
    ResumeConversation,
    fusionner_reglages,
)
from backend.core import EchoHubError

PREFIXE = "/chat"

routeur = APIRouter(prefix=PREFIXE, tags=["chat"])

_P = ParamSpec("_P")
_R = TypeVar("_R")


def _traduire_erreurs(fonction: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
    """Convertit les erreurs métier en réponses HTTP, en préservant la signature vue par FastAPI."""

    @wraps(fonction)
    async def enveloppe(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return await fonction(*args, **kwargs)
        except EchoHubError as exc:
            logger.warning("{} : {}", fonction.__name__, exc)
            raise HTTPException(status_code=exc.statut_http, detail=exc.to_dict()) from exc

    return enveloppe


@routeur.get("/conversations", response_model=list[ResumeConversation])
@_traduire_erreurs
async def lister_conversations(archivees: bool = Query(default=False)) -> list[ResumeConversation]:
    """Liste les conversations, actives par défaut."""
    return depot.lister_conversations(archivees=archivees)


@routeur.post("/conversations", response_model=ResumeConversation, status_code=status.HTTP_201_CREATED)
@_traduire_erreurs
async def creer_conversation(corps: CreationConversation) -> ResumeConversation:
    """Crée une conversation et ses réglages initiaux."""
    return depot.creer_conversation(corps.titre, corps.modele_id, corps.reglages)


@routeur.get("/conversations/{conversation_id}", response_model=ConversationDetaillee)
@_traduire_erreurs
async def lire_conversation(conversation_id: str) -> ConversationDetaillee:
    """Conversation complète : métadonnées, réglages et historique en une réponse."""
    return ConversationDetaillee(
        conversation=depot.exiger_conversation(conversation_id),
        reglages=depot.lire_reglages(conversation_id),
        messages=depot.lister_messages(conversation_id),
    )


@routeur.patch("/conversations/{conversation_id}", response_model=ResumeConversation)
@_traduire_erreurs
async def modifier_conversation(conversation_id: str, corps: MajConversation) -> ResumeConversation:
    """Renomme, archive ou change le modèle par défaut d'une conversation."""
    return depot.maj_conversation(conversation_id, corps)


@routeur.delete("/conversations/{conversation_id}")
@_traduire_erreurs
async def supprimer_conversation(conversation_id: str) -> dict[str, bool]:
    """Supprime la conversation, ses messages et ses réglages, après avoir arrêté toute génération."""
    annulation.annuler(conversation_id)
    depot.supprimer_conversation(conversation_id)
    return {"supprimee": True}


@routeur.get("/conversations/{conversation_id}/reglages", response_model=ReglagesConversation)
@_traduire_erreurs
async def lire_reglages(conversation_id: str) -> ReglagesConversation:
    """Prompt système et paramètres d'échantillonnage de la conversation."""
    depot.exiger_conversation(conversation_id)
    return depot.lire_reglages(conversation_id)


@routeur.patch("/conversations/{conversation_id}/reglages", response_model=ReglagesConversation)
@_traduire_erreurs
async def modifier_reglages(conversation_id: str, corps: MajReglages) -> ReglagesConversation:
    """Fusionne un patch partiel avec les réglages existants. Fournir tous les champs équivaut à un remplacement."""
    actuels = depot.lire_reglages(conversation_id)
    return depot.ecrire_reglages(conversation_id, fusionner_reglages(actuels, corps))


@routeur.get("/conversations/{conversation_id}/messages", response_model=list[MessageChat])
@_traduire_erreurs
async def lister_messages(conversation_id: str) -> list[MessageChat]:
    """Historique complet, dans l'ordre d'écriture."""
    depot.exiger_conversation(conversation_id)
    return depot.lister_messages(conversation_id)


@routeur.delete("/conversations/{conversation_id}/messages")
@_traduire_erreurs
async def vider_messages(conversation_id: str) -> dict[str, int]:
    """Vide l'historique en conservant la conversation et ses réglages."""
    return {"supprimes": depot.supprimer_messages(conversation_id)}


@routeur.post("/conversations/{conversation_id}/generer", response_class=StreamingResponse)
@_traduire_erreurs
async def generer(conversation_id: str, corps: DemandeGeneration) -> StreamingResponse:
    """Ouvre un flux SSE de génération.

    La préparation est faite avant de rendre la réponse : une conversation inconnue ou une
    génération déjà en cours restent de vrais statuts HTTP (404, 409). Passé ce point, les en-têtes
    sont partis et tout échec devient un événement `erreur` dans le flux.
    """
    preparation = generation.preparer(conversation_id, corps)
    return StreamingResponse(
        _encoder_flux(preparation),
        media_type=flux_sse.TYPE_MEDIA_SSE,
        headers=flux_sse.ENTETES_SSE,
    )


async def _encoder_flux(preparation: generation.PreparationGeneration) -> AsyncIterator[str]:
    async for evenement in generation.diffuser(preparation):
        yield flux_sse.encoder(evenement)


@routeur.post("/conversations/{conversation_id}/annuler")
@_traduire_erreurs
async def annuler_generation(conversation_id: str) -> dict[str, bool]:
    """Demande l'arrêt de la génération en cours. `annulee` vaut `false` s'il n'y en avait aucune."""
    depot.exiger_conversation(conversation_id)
    return {"annulee": annulation.annuler(conversation_id)}
