"""Routes HTTP du domaine `engines`.

Le routeur fait partie de la tranche verticale du domaine : ce qui change ensemble vit ensemble.
L'application n'a qu'à l'inclure sous son préfixe `/api` — elle n'a rien à savoir de la façon dont
les moteurs sont installés ou sondés.

Le flux d'installation est exposé en SSE sur un **GET**, malgré la nature non idempotente de
l'opération : `EventSource`, côté navigateur, ne sait émettre que des GET. L'alternative — un POST
consommé par `fetch` et un `ReadableStream` — ferait porter au frontend une plomberie que ce
protocole évite. Le choix est assumé et documenté ici plutôt que subi.

Fermer le flux annule l'installation : le générateur du domaine est clos, son `finally` coupe le
sous-processus et supprime le venv partiel.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger

from backend.core import EchoHubError
from backend.engines import service
from backend.engines.modeles import EtatMoteurs, EvenementInstallation, SanteMoteur, VersionVllm

router = APIRouter(prefix="/engines", tags=["engines"])


def _echec(exc: EchoHubError) -> HTTPException:
    """Traduit une erreur métier en réponse HTTP en conservant remédiation et détails."""
    return HTTPException(status_code=exc.statut_http, detail=exc.to_dict())


@router.get("/etat", response_model=EtatMoteurs, summary="État de santé de tous les moteurs")
async def lire_etat(
    forcer_llamacpp: bool = Query(default=False, description="Relancer la sonde llama.cpp."),
    verifier_vllm: bool = Query(default=False, description="Sonder chaque venv vLLM (lent)."),
) -> EtatMoteurs:
    try:
        return await service.etat_des_moteurs(forcer_llamacpp=forcer_llamacpp, verifier_vllm=verifier_vllm)
    except EchoHubError as exc:
        raise _echec(exc) from exc


@router.get("/llamacpp/sante", response_model=SanteMoteur, summary="Santé du binaire llama.cpp")
async def lire_sante_llamacpp(
    forcer: bool = Query(default=False, description="Ignorer la dernière mesure et resonder."),
) -> SanteMoteur:
    try:
        return await service.sante_llamacpp(forcer=forcer)
    except EchoHubError as exc:
        raise _echec(exc) from exc


@router.get("/vllm/versions", response_model=list[VersionVllm], summary="Versions de vLLM installées")
async def lister_versions_vllm(
    verifier: bool = Query(default=False, description="Sonder chaque venv au lieu de lire le marqueur."),
) -> list[VersionVllm]:
    try:
        return await service.versions_vllm(verifier=verifier)
    except EchoHubError as exc:
        raise _echec(exc) from exc


def _encoder(evenement: EvenementInstallation) -> str:
    """Un événement SSE. `ensure_ascii=False` conserve les accents des messages français."""
    return f"data: {evenement.model_dump_json()}\n\n"


async def _flux_installation(version: str, remplacer: bool) -> AsyncIterator[str]:
    """Relaie les événements du domaine. Une erreur métier devient un dernier événement, pas un 500.

    Le statut HTTP est déjà émis quand l'installation démarre : signaler l'échec dans le flux est
    la seule façon pour le client d'en connaître la cause.
    """
    flux = service.installer_vllm(version, remplacer=remplacer)
    try:
        async for evenement in flux:
            yield _encoder(evenement)
    except EchoHubError as exc:
        logger.error("Flux d'installation vLLM {} interrompu : {}", version, exc)
        yield f"data: {json.dumps(exc.to_dict(), ensure_ascii=False)}\n\n"
    finally:
        # Déconnexion du client : ce générateur-ci est fermé, mais celui du domaine ne le serait
        # qu'au ramasse-miettes. Le fermer explicitement déclenche l'annulation immédiate.
        await flux.aclose()


@router.get("/vllm/versions/{version}/installation", summary="Installer une version (flux SSE)")
async def installer_version_vllm(
    version: str,
    remplacer: bool = Query(default=False, description="Réinstaller une version déjà validée."),
) -> StreamingResponse:
    return StreamingResponse(
        _flux_installation(version, remplacer),
        media_type="text/event-stream",
        # Sans cet en-tête, un proxy tamponnant retiendrait le flux et l'interface n'afficherait
        # rien pendant toute l'installation, puis tout d'un coup.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/vllm/versions/{version}/installation", summary="Annuler l'installation en cours")
async def annuler_installation(version: str) -> dict[str, bool]:
    try:
        return {"annulee": service.annuler_installation_vllm(version)}
    except EchoHubError as exc:
        raise _echec(exc) from exc


@router.delete("/vllm/versions/{version}", summary="Supprimer une version installée")
async def supprimer_version(version: str) -> dict[str, str]:
    try:
        service.supprimer_version_vllm(version)
    except EchoHubError as exc:
        raise _echec(exc) from exc
    return {"version": version, "etat": "supprimee"}
