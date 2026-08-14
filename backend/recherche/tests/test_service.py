"""Orchestration de la recherche : pagination bornée, dédoublonnage, verdict d'échec.

Aucun réseau : un client factice rejoue des charges JSON scriptées, et compte les appels. C'est la
même exigence que le planificateur testable sans GPU — les décisions du service doivent être
vérifiables sans dépendre d'un service en face.

Les coroutines sont pilotées par `asyncio.run` plutôt que par un marqueur `pytest.mark.asyncio` :
le dépôt ne configure nulle part `asyncio_mode`, et un test qui dépend d'une configuration absente
est un test qui peut être silencieusement ignoré.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.recherche.client_searxng import ClientSearxng
from backend.recherche.erreurs import RechercheEchouee
from backend.recherche.modeles import ParametresRecherche, ReponseRecherche, SanteRecherche
from backend.recherche.service import rechercher, sonder

_URL_TEST = "http://searxng:8080"


def _resultat(indice: int) -> dict[str, Any]:
    """Une entrée SearXNG minimale mais complète — seule l'URL distingue deux entrées."""
    return {"url": f"https://example.org/{indice}", "title": f"Résultat {indice}", "engine": "duckduckgo"}


def _page(*indices: int, muets: list[Any] | None = None) -> dict[str, Any]:
    return {"results": [_resultat(i) for i in indices], "unresponsive_engines": muets or []}


class ClientFactice(ClientSearxng):
    """Client scripté : rend les charges dans l'ordre, retient les pages demandées."""

    def __init__(self, charges: list[dict[str, Any]]) -> None:
        super().__init__(_URL_TEST, 1.0)
        self._charges = charges
        self.pages_demandees: list[int] = []

    async def interroger(self, parametres: ParametresRecherche, page: int) -> dict[str, Any]:
        self.pages_demandees.append(page)
        indice = min(page - 1, len(self._charges) - 1)
        return self._charges[indice]


def _lancer(charges: list[dict[str, Any]], nombre: int = 10) -> tuple[ReponseRecherche, ClientFactice]:
    client = ClientFactice(charges)
    parametres = ParametresRecherche(requete="rtx 5080", nombre_resultats=nombre)
    reponse = asyncio.run(rechercher(parametres, client=client))
    return reponse, client


def test_une_seule_page_suffit_quand_le_nombre_demande_est_atteint() -> None:
    reponse, client = _lancer([_page(1, 2, 3)], nombre=3)

    assert client.pages_demandees == [1]
    assert len(reponse.resultats) == 3
    assert reponse.pages_interrogees == 1


def test_pagination_bornee_a_trois_pages() -> None:
    """Chaque page apporte du neuf : la borne, et rien d'autre, doit arrêter la boucle."""
    charges = [_page(1, 2), _page(3, 4), _page(5, 6), _page(7, 8)]
    reponse, client = _lancer(charges, nombre=50)

    assert client.pages_demandees == [1, 2, 3]
    assert len(reponse.resultats) == 6
    assert reponse.pages_interrogees == 3


def test_page_sans_nouveaute_arrete_la_pagination() -> None:
    """Des moteurs qui se répètent ne justifient pas un aller-retour de plus."""
    reponse, client = _lancer([_page(1, 2), _page(1, 2)], nombre=50)

    assert client.pages_demandees == [1, 2]
    assert len(reponse.resultats) == 2


def test_dedoublonnage_par_url_entre_pages() -> None:
    reponse, _ = _lancer([_page(1, 2), _page(2, 3)], nombre=50)

    urls = [resultat.url for resultat in reponse.resultats]
    assert urls == ["https://example.org/1", "https://example.org/2", "https://example.org/3"]


def test_troncature_au_nombre_demande_sans_completion() -> None:
    """Le nombre demandé est un plafond : on coupe ce qui dépasse, on n'invente rien pour l'atteindre."""
    reponse, _ = _lancer([_page(1, 2, 3, 4, 5)], nombre=2)

    assert len(reponse.resultats) == 2


def test_zero_resultat_avec_moteurs_muets_leve() -> None:
    """C'est la panne qui doit remonter, pas une liste vide qui la ferait passer pour un constat."""
    client = ClientFactice([_page(muets=[["google", "timeout"], ["brave", "timeout"]])])
    parametres = ParametresRecherche(requete="rtx 5080")

    with pytest.raises(RechercheEchouee) as echec:
        asyncio.run(rechercher(parametres, client=client))

    assert echec.value.statut_http == 502
    assert "google" in echec.value.details["moteurs_muets"]


def test_zero_resultat_sans_moteur_muet_est_une_mesure_valide() -> None:
    """Les moteurs ont répondu et n'ont rien : c'est une réponse, pas une erreur."""
    reponse, _ = _lancer([_page()], nombre=10)

    assert reponse.resultats == ()
    assert reponse.moteurs_muets == ()
    assert reponse.duree_ms is not None


def test_moteurs_muets_exposes_quand_la_reponse_est_partielle() -> None:
    """Une réponse dégradée doit se voir : des résultats accompagnés de moteurs muets restent partiels."""
    reponse, _ = _lancer([_page(1, muets=[["google", "timeout"]])], nombre=1)

    assert len(reponse.resultats) == 1
    assert [muet.moteur for muet in reponse.moteurs_muets] == ["google"]


def test_sonde_complete_ne_declenche_pas_de_recherche_si_le_service_est_muet() -> None:
    """Inutile d'interroger les moteurs quand la racine du service ne répond déjà pas."""

    class ClientEteint(ClientFactice):
        async def sonder(self) -> SanteRecherche:
            return SanteRecherche(disponible=False, url=_URL_TEST, detail="connexion refusée")

    client = ClientEteint([_page(1)])
    sante = asyncio.run(sonder(complet=True, client=client))

    assert sante.disponible is False
    assert client.pages_demandees == []
