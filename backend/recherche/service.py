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
from backend.recherche.cache import CacheRecherches, cache
from backend.recherche.client_searxng import ClientSearxng
from backend.recherche.pool_moteurs import MOTEURS_PAR_APPEL_DEFAUT, TirageMoteurs, tirage
from backend.recherche.erreurs import RechercheEchouee
from backend.recherche.modeles import (
    CategorieRecherche,
    PageRecherche,
    ParametresRecherche,
    ReponseRecherche,
    ResultatRecherche,
    SanteRecherche,
    maintenant_utc,
)

# Borne haute du nombre de pages interrogées pour une recherche.
#
# RAMENÉE DE 3 À 2 le 2026-08-26, et ce n'est pas un réglage de confort. Une page n'est pas une
# requête sortante : c'en est UNE PAR MOTEUR. À trois pages, une seule recherche consommait trois
# appels sur chaque moteur du pool — et un moteur scrapé se fait suspendre en quelques unités
# (mesuré : `yep` rend 20 résultats au premier appel, « access denied » au troisième). La
# pagination était donc le principal multiplicateur du rate-limit constaté ce jour-là.
#
# Deux pages suffisent au plafond usuel de 10 à 20 résultats, et la boucle s'arrête de toute façon
# dès qu'une page n'apporte plus rien de neuf ou que le compte est atteint.
_PAGES_MAX: Final = 2

# Requête témoin de la sonde complète : courte, sans accent, sans intérêt commercial — elle sert
# uniquement à prouver que la chaîne HTTP + JSON + moteurs fonctionne de bout en bout.
_REQUETE_SONDE: Final = "echohub"

# Relances autorisées quand le lot tiré revient entièrement muet. Une seule, et c'est un choix :
# les moteurs muets viennent d'être écartés par `signaler_muets`, donc le tirage suivant en donne
# d'AUTRES — la relance interroge un lot neuf, pas le même une seconde fois. Au-delà d'une, on
# transformerait une panne du pool en rafale, ce qui est précisément ce qu'on cherche à éviter.
_RELANCES_MAX: Final = 1


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
    tirage_moteurs: TirageMoteurs | None = None,
    cache_recherches: CacheRecherches | None = None,
) -> ReponseRecherche:
    """Exécute une recherche complète. Lève plutôt que de rendre une liste vide sur panne.

    Le tirage et le cache sont injectables au même titre que le client : ils portent l'état qui
    protège du rate-limit, et un test qui ne peut pas les remplacer ne peut pas prouver qu'ils
    fonctionnent.
    """
    memoire = cache_recherches if cache_recherches is not None else cache()
    connue = memoire.lire(parametres)
    if connue is not None:
        return connue

    debut = time.perf_counter()
    collecte = await _collecter_avec_relance(
        parametres,
        client or construire_client(),
        tirage_moteurs if tirage_moteurs is not None else tirage(),
    )
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
    reponse = _assembler(parametres, collecte, duree_ms)
    memoire.ecrire(parametres, reponse)
    return reponse


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


async def _collecter_avec_relance(
    parametres: ParametresRecherche, client: ClientSearxng, tirage_moteurs: TirageMoteurs
) -> _Collecte:
    """Collecte, et rejoue une fois sur un lot neuf si le premier est revenu entièrement muet.

    Sans cette relance, la redondance du pool ne servirait qu'à la recherche SUIVANTE : celle-ci
    échouerait quand même, et le modèle écrirait « la recherche n'a pas fonctionné » alors que
    treize moteurs disponibles n'ont jamais été sollicités. C'est exactement le scénario mesuré le
    2026-08-26, où l'échec du harnais a poussé le modèle à inventer.
    """
    collecte = await _collecter(parametres, client, tirage_moteurs)
    for tentative in range(1, _RELANCES_MAX + 1):
        if collecte.resultats or not collecte.premiere_page.moteurs_muets:
            return collecte
        logger.warning(
            "recherche « {} » : lot muet, relance {} sur un autre lot ({} moteur(s) encore disponible(s))",
            parametres.requete, tentative, tirage_moteurs.disponibles(),
        )
        collecte = await _collecter(parametres, client, tirage_moteurs)
    return collecte


async def _collecter(
    parametres: ParametresRecherche, client: ClientSearxng, tirage_moteurs: TirageMoteurs
) -> _Collecte:
    """Parcourt les pages jusqu'au nombre demandé, sans jamais dépasser `_PAGES_MAX`."""
    moteurs = _moteurs_du_tour(parametres, tirage_moteurs)
    resultats: list[ResultatRecherche] = []
    urls_vues: set[str] = set()
    premiere: PageRecherche | None = None
    pages = 0

    for page in range(1, _PAGES_MAX + 1):
        courante = analyser_page(await client.interroger(parametres, page, moteurs))
        premiere = premiere if premiere is not None else courante
        pages = page
        tirage_moteurs.signaler_muets(courante.moteurs_muets)
        ajoutes = _fusionner(resultats, urls_vues, courante.resultats)
        # Deux raisons d'arrêter, et la troisième est nouvelle. Une page qui n'apporte plus rien de
        # neuf signale la fin utile : les moteurs se répètent. Le compte atteint aussi. Et un
        # moteur qui vient de refuser l'accès ne dira pas oui à la page suivante : insister est la
        # seule action strictement perdante — rien à gagner, et la suspension qui s'allonge.
        if ajoutes == 0 or len(resultats) >= parametres.nombre_resultats or courante.moteurs_muets:
            break

    return _Collecte(resultats=resultats, premiere_page=premiere or PageRecherche(), pages=pages)


def _moteurs_du_tour(parametres: ParametresRecherche, tirage_moteurs: TirageMoteurs) -> tuple[str, ...]:
    """Les moteurs nommés pour cette recherche, ou rien pour laisser SearXNG décider.

    Le pool n'est mesuré que pour `general` — c'est là que le rate-limit a frappé, et prétendre
    qu'une liste vérifiée sur des requêtes web vaut pour les images ou la musique serait une
    supposition déguisée en réglage. Les autres catégories gardent le catalogue par défaut.
    """
    if parametres.categorie is not CategorieRecherche.GENERAL:
        return ()
    moteurs = tirage_moteurs.choisir(MOTEURS_PAR_APPEL_DEFAUT)
    logger.debug("recherche « {} » confiée à : {}", parametres.requete, ", ".join(moteurs))
    return moteurs


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
