"""Routes HTTP du domaine `fichiers`.

Deux routes, sans préfixe commun :

- l'envoi est rattaché à l'espace des conversations (`/conversations/{id}/fichiers`), cohérent
  avec les routes existantes du domaine `chat` (`/chat/conversations/{id}/...`) ;
- le service est indépendant de toute conversation (`/fichiers/{id}`) — c'est la MÊME route pour
  un artefact produit par le modèle et pour une pièce jointe de l'utilisateur, comme l'exige le
  plan d'exécution (section 2.1).

Traduction des erreurs : même contrat que `backend.chat.routes` (`EchoHubError` -> `HTTPException`
via `statut_http` et `to_dict()`), dupliqué ici à dessein — deux domaines indépendants, pas une
même raison de changer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from loguru import logger

from backend.core import EchoHubError
from backend.fichiers import service
from backend.fichiers.modeles import FichierConversation, OrigineFichier

routeur = APIRouter(tags=["fichiers"])

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


@routeur.post("/conversations/{conversation_id}/fichiers", response_model=FichierConversation)
@_traduire_erreurs
async def deposer_fichier(
    conversation_id: str,
    fichier: UploadFile,
    origine: OrigineFichier = Form(default="utilisateur"),
    message_id: str | None = Form(default=None),
) -> FichierConversation:
    """Dépose un fichier dans le magasin de la conversation. Quotas et type MIME vérifiés avant écriture."""
    octets = await fichier.read()
    return service.deposer_fichier(
        conversation_id,
        nom_fourni=fichier.filename or "fichier",
        type_mime_declare=fichier.content_type,
        octets=octets,
        origine=origine,
        message_id=message_id,
    )


@routeur.get("/fichiers/{fichier_id}")
@_traduire_erreurs
async def servir_fichier(fichier_id: str) -> FileResponse:
    """Sert le fichier référencé — même route pour un artefact produit et pour une pièce jointe."""
    fichier = service.lire_fichier(fichier_id)
    chemin = service.chemin_disque(fichier)
    return FileResponse(path=chemin, media_type=fichier.type_mime, filename=fichier.nom_affiche)
