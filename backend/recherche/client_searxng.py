"""Frontière réseau du domaine `recherche` : le seul module qui parle à SearXNG.

Tout le reste du domaine est pur. Concentrer ici le transport HTTP donne trois choses : un seul
endroit à protéger par try/except, un seul endroit à journaliser, et un service testable en
injectant un client factice.

Le client est créé par appel (`async with httpx.AsyncClient(...)`), comme l'adaptateur vLLM du
domaine `inference`. Une recherche est un événement rare et court : mutualiser un client persistant
imposerait un cycle de vie à gérer dans `main.py` pour un gain nul.

Deux échecs, deux erreurs distinctes : injoignable (`RechercheIndisponible`) et réponse
inexploitable (`RechercheEchouee`). Aucun des deux ne dégénère en liste vide.
"""

from __future__ import annotations

import time
from typing import Any, Final

import httpx
from loguru import logger

from backend.recherche.erreurs import RechercheEchouee, RechercheIndisponible
from backend.recherche.modeles import ParametresRecherche, SanteRecherche, maintenant_utc

_CHEMIN_RECHERCHE: Final = "/search"

# La sonde interroge la racine du service : elle doit rester bien plus courte que le délai d'une
# recherche, sinon un écran qui affiche l'état bloque plus longtemps que la fonction elle-même.
_DELAI_SONDE_S: Final = 3.0

_ENTETES_RECHERCHE: Final[dict[str, str]] = {
    "User-Agent": "EchoHub/2.0 (recherche locale)",
    "Accept": "application/json",
}
_ENTETES_SONDE: Final[dict[str, str]] = {"User-Agent": "EchoHub/2.0 (sonde)"}

# Un corps d'erreur SearXNG peut être une page HTML entière : on n'en journalise qu'un extrait.
_LONGUEUR_EXTRAIT: Final = 300

_REMEDIATION_403: Final = (
    "SearXNG refuse le format demandé : vérifier que `json` figure dans `search.formats` "
    "de docker/searxng/settings.yml, et que le limiteur est désactivé."
)


class ClientSearxng:
    """Accès HTTP à une instance SearXNG. L'URL vient de la configuration, jamais du code appelant."""

    def __init__(self, url_base: str, delai_s: float) -> None:
        # La barre finale est retirée ici aussi : la configuration la normalise déjà, mais un client
        # construit à la main dans un test ne passerait pas par elle.
        self._url_base = url_base.rstrip("/")
        self._delai_s = delai_s

    @property
    def url_base(self) -> str:
        return self._url_base

    async def interroger(self, parametres: ParametresRecherche, page: int) -> dict[str, Any]:
        """Interroge une page de résultats et rend la charge JSON brute, sans l'interpréter."""
        url = f"{self._url_base}{_CHEMIN_RECHERCHE}"
        try:
            async with httpx.AsyncClient(timeout=self._delai_s, follow_redirects=False) as client:
                reponse = await client.get(url, params=_parametres_http(parametres, page), headers=_ENTETES_RECHERCHE)
        except httpx.TimeoutException as exc:
            logger.error("SearXNG muet après {} s sur {} : {}", self._delai_s, url, exc)
            raise RechercheIndisponible(
                f"Le service de recherche n'a pas répondu en {self._delai_s:.0f} s.",
                details={"url": url, "cause": str(exc)},
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("Appel SearXNG impossible ({}) : {}", type(exc).__name__, exc)
            raise RechercheIndisponible(
                "Service de recherche injoignable.",
                details={"url": url, "cause": str(exc), "type": type(exc).__name__},
            ) from exc
        return _charge_json(reponse)

    async def sonder(self) -> SanteRecherche:
        """Mesure la disponibilité HTTP du service en interrogeant sa racine.

        Ce que la sonde prouve : le conteneur répond à l'URL configurée. Ce qu'elle ne prouve
        **pas** : que le format JSON est activé, ni qu'un moteur fonctionne. Seule une vraie
        recherche le démontre — c'est le rôle de la sonde complète du service.
        """
        debut = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=_DELAI_SONDE_S, follow_redirects=False) as client:
                reponse = await client.get(f"{self._url_base}/", headers=_ENTETES_SONDE)
        except httpx.HTTPError as exc:
            logger.warning("Sonde SearXNG en échec sur {} : {}", self._url_base, exc)
            return SanteRecherche(disponible=False, url=self._url_base, detail=str(exc))

        latence_ms = round((time.perf_counter() - debut) * 1000, 2)
        # 2xx et 3xx valent « le service répond » : une redirection reste une réponse du service.
        disponible = reponse.status_code < 400
        return SanteRecherche(
            disponible=disponible,
            url=self._url_base,
            latence_ms=latence_ms,
            statut_http=reponse.status_code,
            detail="" if disponible else f"La racine du service a répondu {reponse.status_code}.",
            verifie_le=maintenant_utc(),
        )


def _parametres_http(parametres: ParametresRecherche, page: int) -> dict[str, str]:
    """Chaîne de requête SearXNG. `format=json` est ce qui sépare l'API de l'interface web."""
    return {
        "q": parametres.requete,
        "format": "json",
        "categories": parametres.categorie.value,
        "language": parametres.langue,
        "pageno": str(page),
        # Filtrage explicite plutôt qu'implicite : la valeur du fichier de configuration pourrait
        # changer sans que ce domaine le sache, et le comportement doit rester lisible ici.
        "safesearch": "0",
    }


def _charge_json(reponse: httpx.Response) -> dict[str, Any]:
    """Valide le statut puis le corps. Un 403 a une cause connue : le format JSON non autorisé."""
    if reponse.status_code != 200:
        extrait = reponse.text[:_LONGUEUR_EXTRAIT]
        logger.error("SearXNG a répondu {} : {}", reponse.status_code, extrait)
        raise RechercheEchouee(
            f"Le service de recherche a répondu {reponse.status_code}.",
            remediation=_REMEDIATION_403 if reponse.status_code == 403 else "",
            details={"statut": reponse.status_code, "corps": extrait},
        )
    try:
        charge: Any = reponse.json()
    except ValueError as exc:
        logger.error("Corps SearXNG non décodable en JSON : {}", exc)
        raise RechercheEchouee(
            "Réponse du service de recherche illisible (JSON attendu).",
            details={"cause": str(exc)},
        ) from exc
    if not isinstance(charge, dict):
        logger.error("Charge SearXNG inattendue : {} au lieu d'un objet", type(charge).__name__)
        raise RechercheEchouee(
            "Réponse du service de recherche inattendue : objet JSON attendu.",
            details={"type": type(charge).__name__},
        )
    return charge
