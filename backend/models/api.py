"""Routes HTTP du domaine `models` — recherche Hub, registre local, transferts.

Le routeur appartient à la tranche verticale du domaine : il vit à côté du métier qu'il expose et
n'ajoute aucune règle. Toute décision — quoi télécharger, quelles métadonnées sont lisibles, ce
qu'un écart de cohérence signifie — appartient aux modules du domaine ; ici on traduit, on ne
décide pas.

Deux distinctions du domaine sont préservées telles quelles dans les réponses, parce que les
confondre est précisément l'erreur que la v1 commettait :

- ce que le Hub **annonce** (`/recherche`, `/depots/{depot}`) n'est jamais présenté comme mesuré ;
- ce que le fichier **contient** (`/registre/{id}/metadonnees`) est lu dans l'en-tête, et vaut
  `null` quand il n'est pas lisible — jamais une estimation déguisée en mesure.

Ordre de déclaration : les chemins littéraux (`/registre/synchronisation`, `/telechargements/flux`)
précèdent les chemins paramétrés qui les engloberaient. FastAPI retient la première route qui
correspond ; inverser l'ordre ferait passer « synchronisation » pour un identifiant de modèle.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from backend.core import EchoHubError
from backend.models import (
    FormatRecherche,
    MetadonneesGGUF,
    ModeleEnregistre,
    Ordre,
    PageRecherche,
    RapportCoherence,
    ResultatRecherche,
    ResumeSynchronisation,
    Telechargement,
    TriRecherche,
    details,
    gestionnaire,
    lister_modeles,
    metadonnees_modele,
    obtenir_modele,
    oublier_modele,
    rechercher,
    synchroniser_registre,
    verifier_modele_enregistre,
)
from backend.models.download import ETATS_TERMINAUX, INTERVALLE_DIFFUSION_S, MAX_ITERATIONS_DIFFUSION

# Préfixe SANS `/api` : nginx réécrit `/api/(.*)` en `/$1` avant de proxifier (docker/nginx.conf).
router = APIRouter(prefix="/models", tags=["models"])

# Sans `X-Accel-Buffering`, nginx tamponne la réponse et la progression d'un transfert de plusieurs
# gigaoctets n'arrive au navigateur qu'une fois le transfert fini — c'est-à-dire jamais à temps.
ENTETES_FLUX = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


class DemandeTelechargement(BaseModel):
    """Un fichier précis du dépôt, ou le dépôt entier si `fichier` est omis."""

    depot: str = Field(min_length=1)
    fichier: str | None = None
    revision: str = "main"


class ResultatOubli(BaseModel):
    """Réponse explicite plutôt qu'un 204 muet : l'interface affiche ce qui a été fait."""

    oublie: bool


def _en_http(exc: EchoHubError) -> HTTPException:
    """Traduit une erreur métier en réponse HTTP à partir du statut qu'elle porte déjà."""
    return HTTPException(status_code=exc.statut_http, detail=exc.to_dict())


# ------------------------------------------------------------------ recherche sur le Hub


@router.get("/recherche", response_model=PageRecherche)
def rechercher_depots(
    requete: str = Query(default=""),
    formats: list[FormatRecherche] = Query(default_factory=list),
    tri: TriRecherche = Query(default=TriRecherche.TELECHARGEMENTS),
    ordre: Ordre = Query(default="desc"),
    page: int = Query(default=0, ge=0),
    taille_page: int = Query(default=20, ge=1, le=100),
) -> PageRecherche:
    """Page de dépôts du Hub. Tout ce qui revient ici est **annoncé**, rien n'est mesuré."""
    try:
        return rechercher(requete, formats=formats, tri=tri, ordre=ordre, page=page, taille_page=taille_page)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


@router.get("/depots/{depot:path}", response_model=ResultatRecherche)
def fiche_depot(depot: str) -> ResultatRecherche:
    """Fiche complète d'un dépôt. `:path` parce qu'un identifiant Hub contient un `/`."""
    try:
        return details(depot)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


# ------------------------------------------------------------------------- registre local


@router.get("/registre", response_model=list[ModeleEnregistre])
def lister_registre() -> list[ModeleEnregistre]:
    """Modèles présents sur le disque et connus du registre."""
    return lister_modeles()


@router.post("/registre/synchronisation", response_model=ResumeSynchronisation)
def synchroniser() -> ResumeSynchronisation:
    """Réaligne le registre sur le contenu réel du disque — le disque fait autorité."""
    try:
        return synchroniser_registre()
    except EchoHubError as exc:
        raise _en_http(exc) from exc


@router.get("/registre/{identifiant}", response_model=ModeleEnregistre)
def lire_modele(identifiant: str) -> ModeleEnregistre:
    try:
        return obtenir_modele(identifiant)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


@router.delete("/registre/{identifiant}", response_model=ResultatOubli)
def oublier(identifiant: str) -> ResultatOubli:
    """Retire l'entrée du registre. Les fichiers restent sur le disque, délibérément."""
    try:
        oublier_modele(identifiant)
    except EchoHubError as exc:
        raise _en_http(exc) from exc
    return ResultatOubli(oublie=True)


@router.get("/registre/{identifiant}/metadonnees", response_model=MetadonneesGGUF | None)
def lire_metadonnees(identifiant: str) -> MetadonneesGGUF | None:
    """Métadonnées LUES dans l'en-tête GGUF — seule entrée valable du planificateur.

    `null` quand le modèle n'est pas au format GGUF : l'appelant doit décider quoi en faire, il ne
    reçoit jamais une valeur inventée à la place.
    """
    try:
        return metadonnees_modele(identifiant)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


@router.get("/registre/{identifiant}/coherence", response_model=RapportCoherence)
def verifier(identifiant: str) -> RapportCoherence:
    """Confronte ce que le modèle déclare à ce qu'il contient réellement."""
    try:
        return verifier_modele_enregistre(identifiant)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


# ---------------------------------------------------------------------------- transferts


@router.get("/telechargements", response_model=list[Telechargement])
def lister_telechargements() -> list[Telechargement]:
    return gestionnaire().lister()


@router.post("/telechargements", response_model=Telechargement, status_code=202)
def demarrer_telechargement(demande: DemandeTelechargement) -> Telechargement:
    """Démarre le transfert et rend la main aussitôt — la suite se lit sur `/flux`."""
    try:
        return gestionnaire().demarrer(demande.depot, fichier=demande.fichier, revision=demande.revision)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


def _evenement(etat: Telechargement) -> str:
    return f"data: {etat.model_dump_json()}\n\n"


async def _flux_global() -> AsyncIterator[str]:
    """Diffuse l'état de TOUS les transferts, chaque événement portant un état complet.

    État complet et non delta : un client qui se connecte en cours de route n'a rien à
    reconstituer. La boucle est bornée par `MAX_ITERATIONS_DIFFUSION`, exactement comme la
    diffusion par transfert du domaine — un navigateur fermé sans fermer proprement le flux ne doit
    pas laisser une tâche tourner sans fin.
    """
    gest = gestionnaire()
    dernier: str | None = None
    for _ in range(MAX_ITERATIONS_DIFFUSION):
        etats = gest.lister()
        empreinte = "|".join(etat.model_dump_json() for etat in etats)
        if empreinte != dernier:
            dernier = empreinte
            for etat in etats:
                yield _evenement(etat)
        if etats and all(etat.etat in ETATS_TERMINAUX for etat in etats):
            break
        await asyncio.sleep(INTERVALLE_DIFFUSION_S)
    else:
        logger.warning("Diffusion globale des transferts arrêtée sur sa borne d'itérations")
    yield "data: [DONE]\n\n"


@router.get("/telechargements/flux")
async def flux_telechargements() -> StreamingResponse:
    """Progression de tous les transferts en SSE. GET : `EventSource` ne sait pas faire autrement."""
    return StreamingResponse(_flux_global(), media_type="text/event-stream", headers=ENTETES_FLUX)


@router.get("/telechargements/{identifiant}", response_model=Telechargement)
def etat_telechargement(identifiant: str) -> Telechargement:
    try:
        return gestionnaire().etat(identifiant)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


@router.delete("/telechargements/{identifiant}", response_model=Telechargement)
def annuler_telechargement(
    identifiant: str,
    supprimer_fichiers: bool = Query(default=False),
) -> Telechargement:
    """Le défaut CONSERVE les octets déjà écrits : un transfert de plusieurs Go doit pouvoir
    reprendre plutôt que repartir de zéro."""
    try:
        return gestionnaire().annuler(identifiant, supprimer_fichiers=supprimer_fichiers)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


@router.post("/telechargements/{identifiant}/relance", response_model=Telechargement)
def relancer_telechargement(identifiant: str) -> Telechargement:
    """Reprend un transfert interrompu là où il s'était arrêté."""
    try:
        return gestionnaire().relancer(identifiant)
    except EchoHubError as exc:
        raise _en_http(exc) from exc


@router.get("/telechargements/{identifiant}/flux")
async def flux_telechargement(identifiant: str) -> StreamingResponse:
    """Progression d'un transfert précis — la diffusion native du domaine."""

    async def flux() -> AsyncIterator[str]:
        try:
            async for etat in gestionnaire().suivre(identifiant):
                yield _evenement(etat)
        except EchoHubError as exc:
            logger.error("Diffusion de {} interrompue : {}", identifiant, exc)
            yield f"data: {exc.to_dict()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(flux(), media_type="text/event-stream", headers=ENTETES_FLUX)
