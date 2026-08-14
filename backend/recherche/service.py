"""Orchestration du domaine `recherche` : pagination bornée, dédoublonnage, verdict d'échec.

Trois décisions structurantes, toutes justifiées par la doctrine du projet :

1. **SearXNG ne sait pas rendre « N résultats ».** Il rend une page fusionnée dont la taille dépend
   des moteurs qui ont répondu. Le nombre demandé est donc obtenu en paginant, puis en tronquant —
   et le nombre réellement rendu peut être inférieur. On ne complète jamais pour atteindre N.
2. **La pagination est bornée** (`_PAGES_MAX`) et s'arrête dès qu'une page n'apporte plus rien de
   neuf. Une boucle de sondage sans borne bloquerait le backend sur un moteur bavard.
3. **Zéro résultat n'est pas toujours un constat.** Zéro résultat *avec* des moteurs muets est une
   panne : elle lève. Zéro résultat *sans* moteur muet est une vraie mesure : les moteurs ont
   répondu, ils n'ont rien. Confondre les deux, c'est exactement rendre une liste vide silencieuse.

Le client est injectable : c'est le seul point réseau, et le service doit rester testable sans
service en face — même exigence que le planificateur testable sans GPU.
"""

from __future__ import annotations

import time
from typing import Final

from loguru import logger
from pydantic import BaseModel, Field

from backend.core import EchoHubError, get_settings
from backend.recherche.analyse import analyser_page
from backend.recherche.client_searxng import ClientSearxng
from backend.recherche.erreurs import RechercheEchouee
from backend.recherche.modeles import (
    PageRecherche,
    ParametresRecherche,
    ReponseRecherche,
    ResultatRecherche,
    SanteRecherche,
    maintenant_utc,
)

# Borne haute du nombre de pages interrogées pour une recherche. Trois pages couvrent largement le
# plafond de 50 résultats quand les moteurs répondent ; au-delà, le coût réseau croît sans que la
# pertinence suive. La valeur est un arbitrage assumé, pas une mesure : elle est donc ici, seule et
# nommée, plutôt que dispersée dans le code.
_PAGES_MAX: Final = 3

# Requête témoin de la sonde complète : courte, sans accent, sans intérêt commercial — elle sert
# uniquement à prouver que la chaîne HTTP + JSON + moteurs fonctionne de bout en bout.
_REQUETE_SONDE: Final = "echohub"


def construire_client() -> ClientSearxng:
    """Client bâti sur la configuration : l'URL de SearXNG n'est jamais écrite dans le code."""
    parametres = get_settings()
    return ClientSearxng(parametres.searxng_url, parametres.searxng_timeout_s)


class _Collecte(BaseModel):
    """Agrégat interne des pages parcourues. Interne au module : rien ne l'expose hors du domaine."""

    resultats: list[ResultatRecherche] = Field(default_factory=list)
    # Les suggestions, réponses directes et moteurs muets sont pris sur la première page : ce sont
    # des métadonnées de requête, pas de page. Les fusionner sur trois pages les dupliquerait.
    premiere_page: PageRecherche = Field(default_factory=PageRecherche)
    pages: int = 0


async def rechercher(
    parametres: ParametresRecherche,
    *,
    client: ClientSearxng | None = None,
) -> ReponseRecherche:
    """Exécute une recherche complète. Lève plutôt que de rendre une liste vide sur panne."""
    debut = time.perf_counter()
    collecte = await _collecter(parametres, client or construire_client())
    duree_ms = round((time.perf_counter() - debut) * 1000, 2)

    _refuser_echec_silencieux(parametres, collecte)
    logger.info(
        "recherche « {} » : {} résultat(s) en {} ms ({} page(s), {} moteur(s) muet(s))",
        parametres.requete,
        len(collecte.resultats),
        duree_ms,
        collecte.pages,
        len(collecte.premiere_page.moteurs_muets),
    )
    return _assembler(parametres, collecte, duree_ms)


async def sonder(*, complet: bool = False, client: ClientSearxng | None = None) -> SanteRecherche:
    """Disponibilité du service. `complet` va jusqu'à une vraie recherche témoin.

    La sonde rapide ne mesure que la joignabilité HTTP ; elle ne dit rien du format JSON ni des
    moteurs. C'est explicitement la limite de ce que la racine du service permet de constater.
    """
    effectif = client or construire_client()
    sante = await effectif.sonder()
    if not complet or not sante.disponible:
        return sante
    return await _sonde_complete(effectif, sante)


async def _sonde_complete(client: ClientSearxng, sante: SanteRecherche) -> SanteRecherche:
    """Vérifie la chaîne entière — format JSON activé et moteurs compris — par une recherche réelle."""
    parametres = ParametresRecherche(requete=_REQUETE_SONDE, nombre_resultats=1)
    try:
        reponse = await rechercher(parametres, client=client)
    except EchoHubError as exc:
        logger.warning("Sonde complète de la recherche en échec : {}", exc)
        return sante.model_copy(update={"disponible": False, "detail": str(exc)})
    detail = f"Recherche témoin : {len(reponse.resultats)} résultat(s) en {reponse.duree_ms} ms."
    return sante.model_copy(update={"detail": detail})


async def _collecter(parametres: ParametresRecherche, client: ClientSearxng) -> _Collecte:
    """Parcourt les pages jusqu'au nombre demandé, sans jamais dépasser `_PAGES_MAX`."""
    resultats: list[ResultatRecherche] = []
    urls_vues: set[str] = set()
    premiere: PageRecherche | None = None
    pages = 0

    for page in range(1, _PAGES_MAX + 1):
        courante = analyser_page(await client.interroger(parametres, page))
        premiere = premiere if premiere is not None else courante
        pages = page
        ajoutes = _fusionner(resultats, urls_vues, courante.resultats)
        # Une page qui n'apporte plus rien de neuf signale la fin utile de la pagination : les
        # moteurs se répètent. Continuer coûterait un aller-retour pour un doublon de plus.
        if ajoutes == 0 or len(resultats) >= parametres.nombre_resultats:
            break

    return _Collecte(resultats=resultats, premiere_page=premiere or PageRecherche(), pages=pages)


def _fusionner(
    resultats: list[ResultatRecherche],
    urls_vues: set[str],
    nouveaux: tuple[ResultatRecherche, ...],
) -> int:
    """Ajoute les résultats inédits (dédoublonnage par URL) et rend le nombre réellement ajouté."""
    ajoutes = 0
    for resultat in nouveaux:
        if resultat.url in urls_vues:
            continue
        urls_vues.add(resultat.url)
        resultats.append(resultat)
        ajoutes += 1
    return ajoutes


def _refuser_echec_silencieux(parametres: ParametresRecherche, collecte: _Collecte) -> None:
    """Zéro résultat avec des moteurs muets est une panne : elle doit se voir, pas se taire."""
    muets = collecte.premiere_page.moteurs_muets
    if collecte.resultats or not muets:
        return
    noms = ", ".join(muet.moteur for muet in muets)
    logger.error("recherche « {} » sans résultat, moteurs muets : {}", parametres.requete, noms)
    raise RechercheEchouee(
        "Aucun moteur de recherche n'a répondu.",
        details={"requete": parametres.requete, "moteurs_muets": noms},
    )


def _assembler(parametres: ParametresRecherche, collecte: _Collecte, duree_ms: float) -> ReponseRecherche:
    """Assemble la réponse métier. La troncature est la seule transformation appliquée aux résultats."""
    page = collecte.premiere_page
    return ReponseRecherche(
        requete=parametres.requete,
        categorie=parametres.categorie,
        langue=parametres.langue,
        resultats=tuple(collecte.resultats[: parametres.nombre_resultats]),
        reponses_directes=page.reponses_directes,
        suggestions=page.suggestions,
        moteurs_muets=page.moteurs_muets,
        nombre_annonce=page.nombre_annonce,
        pages_interrogees=collecte.pages,
        duree_ms=duree_ms,
        interroge_le=maintenant_utc(),
    )
