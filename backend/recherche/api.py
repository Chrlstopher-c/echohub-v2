"""Routes HTTP du domaine `recherche`.

Le routeur ne porte pas le préfixe `/api` : la couche d'assemblage (`main.py`) le monte, comme pour
les autres domaines. Les URL publiques sont donc `/api/recherche` et `/api/recherche/sante`.

Deux routes, deux usages nettement séparés :
- la recherche elle-même, entièrement paramétrée par la chaîne de requête ;
- une sonde de disponibilité, que l'interface peut appeler sans déclencher d'appel aux moteurs.

Les contraintes de validation sont déclarées sur les `Query` — FastAPI rend alors un 422 détaillé
avant même d'entrer dans le domaine — et re-vérifiées par `ParametresRecherche`, qui reste la seule
forme acceptée par le service.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from backend.core import EchoHubError
from backend.recherche import service
from backend.recherche.modeles import (
    LANGUE_TOUTES,
    LONGUEUR_REQUETE_MAX,
    MOTIF_LANGUE,
    NOMBRE_RESULTATS_DEFAUT,
    NOMBRE_RESULTATS_MAX,
    CategorieRecherche,
    ParametresRecherche,
    ReponseRecherche,
    SanteRecherche,
)

routeur = APIRouter(prefix="/recherche", tags=["recherche"])


def _echec(exc: EchoHubError) -> HTTPException:
    """Traduit une erreur métier en réponse HTTP en conservant remédiation et détails."""
    return HTTPException(status_code=exc.statut_http, detail=exc.to_dict())


def _valider(requete: str, categorie: CategorieRecherche, langue: str, nombre: int) -> ParametresRecherche:
    """Garde-fou : les contraintes des `Query` reflètent celles du modèle, ceci couvre leur divergence."""
    try:
        return ParametresRecherche(
            requete=requete,
            categorie=categorie,
            langue=langue,
            nombre_resultats=nombre,
        )
    except ValidationError as exc:
        # Les erreurs pydantic sont reformulées en chaînes : leur forme brute embarque un `ctx`
        # pouvant contenir l'exception d'origine, non sérialisable en JSON — la réponse d'erreur
        # deviendrait alors un 500, ce qui masquerait la vraie cause.
        motifs = [f"{'.'.join(str(part) for part in erreur['loc'])} : {erreur['msg']}" for erreur in exc.errors()]
        raise HTTPException(
            status_code=422,
            detail={"code": "parametres_invalides", "message": " ; ".join(motifs)},
        ) from exc


@routeur.get("", response_model=ReponseRecherche, summary="Recherche web via SearXNG")
async def rechercher_web(
    requete: str = Query(alias="q", min_length=1, max_length=LONGUEUR_REQUETE_MAX, description="Termes recherchés."),
    categorie: CategorieRecherche = Query(default=CategorieRecherche.GENERAL, description="Catégorie SearXNG."),
    langue: str = Query(default=LANGUE_TOUTES, pattern=MOTIF_LANGUE, description="`all`, `auto`, `fr` ou `fr-FR`."),
    nombre: int = Query(
        default=NOMBRE_RESULTATS_DEFAUT,
        ge=1,
        le=NOMBRE_RESULTATS_MAX,
        description="Plafond de résultats. Le nombre rendu peut être inférieur : il n'est jamais complété.",
    ),
) -> ReponseRecherche:
    """Interroge SearXNG et rend les résultats mesurés, moteurs muets compris."""
    parametres = _valider(requete, categorie, langue, nombre)
    try:
        return await service.rechercher(parametres)
    except EchoHubError as exc:
        raise _echec(exc) from exc


@routeur.get("/sante", response_model=SanteRecherche, summary="Disponibilité du service de recherche")
async def lire_sante(
    complet: bool = Query(
        default=False,
        description="Aller jusqu'à une recherche témoin — seule façon de prouver que le format JSON est actif.",
    ),
) -> SanteRecherche:
    """Mesure la joignabilité de SearXNG. Ne lève pas sur service éteint : l'état fait partie de la réponse."""
    try:
        return await service.sonder(complet=complet)
    except EchoHubError as exc:
        raise _echec(exc) from exc
