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

from backend.recherche.cache import CacheRecherches
from backend.recherche.client_searxng import ClientSearxng
from backend.recherche.erreurs import RechercheEchouee
from backend.recherche.modeles import ParametresRecherche, ReponseRecherche, SanteRecherche
from backend.recherche.pool_moteurs import MOTEURS_PAR_APPEL_DEFAUT, TirageMoteurs
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
        self.moteurs_demandes: list[tuple[str, ...]] = []

    async def interroger(
        self, parametres: ParametresRecherche, page: int, moteurs: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        self.pages_demandees.append(page)
        self.moteurs_demandes.append(moteurs)
        indice = min(page - 1, len(self._charges) - 1)
        return self._charges[indice]


class ClientSequentiel(ClientFactice):
    """Rend une charge par APPEL, dans l'ordre. La dernière est répétée si les appels débordent."""

    async def interroger(
        self, parametres: ParametresRecherche, page: int, moteurs: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        indice = min(len(self.pages_demandees), len(self._charges) - 1)
        self.pages_demandees.append(page)
        self.moteurs_demandes.append(moteurs)
        return self._charges[indice]


def _lancer(charges: list[dict[str, Any]], nombre: int = 10) -> tuple[ReponseRecherche, ClientFactice]:
    """Chaque appel part d'un tirage et d'un cache NEUFS.

    Sans cela les tests partageraient l'état de processus : un cache rempli par le test précédent
    servirait une réponse sans que le client factice soit appelé, et l'assertion sur les pages
    demandées passerait pour une raison qui n'a rien à voir avec ce qu'elle prétend prouver.
    """
    client = ClientFactice(charges)
    parametres = ParametresRecherche(requete="rtx 5080", nombre_resultats=nombre)
    reponse = asyncio.run(
        rechercher(
            parametres,
            client=client,
            tirage_moteurs=TirageMoteurs(),
            cache_recherches=CacheRecherches(),
        )
    )
    return reponse, client


def test_une_seule_page_suffit_quand_le_nombre_demande_est_atteint() -> None:
    reponse, client = _lancer([_page(1, 2, 3)], nombre=3)

    assert client.pages_demandees == [1]
    assert len(reponse.resultats) == 3
    assert reponse.pages_interrogees == 1


def test_les_moteurs_sont_nommes_explicitement_en_categorie_generale() -> None:
    """Sans `engines`, SearXNG n'utilise que quatre moteurs `general`, dont trois tombent ensemble.

    C'est la protection contre le rate-limit du 2026-08-26 : elle doit se voir dans la requête
    sortante, pas seulement dans l'intention.
    """
    _, client = _lancer([_page(1, 2, 3)], nombre=3)

    assert client.moteurs_demandes[0], "aucun moteur nommé : le pool ne sert à rien"
    assert len(client.moteurs_demandes[0]) == MOTEURS_PAR_APPEL_DEFAUT


def test_une_page_avec_moteur_muet_arrete_la_pagination() -> None:
    """Un moteur qui vient de refuser l'accès ne dira pas oui à la page suivante.

    Insister est la seule action strictement perdante : rien à gagner, et la suspension s'allonge.
    C'était le multiplicateur principal du rate-limit constaté.
    """
    _, client = _lancer([_page(1, muets=[["brave", "CAPTCHA"]]), _page(2)], nombre=10)

    assert client.pages_demandees == [1]


def test_une_recherche_repetee_ne_repart_pas_sur_le_reseau() -> None:
    """Le cas mesuré : six appels identiques d'affilée dans une seule réponse du modèle."""
    client = ClientFactice([_page(1, 2, 3)])
    memoire = CacheRecherches()
    parametres = ParametresRecherche(requete="rtx 5080", nombre_resultats=3)
    for _ in range(3):
        asyncio.run(
            rechercher(parametres, client=client, tirage_moteurs=TirageMoteurs(), cache_recherches=memoire)
        )

    assert client.pages_demandees == [1], "la répétition a coûté des appels réseau"


def test_un_lot_entierement_muet_declenche_une_relance_sur_un_autre_lot() -> None:
    """Sans relance, la redondance du pool ne servirait qu'à la recherche SUIVANTE.

    Celle-ci échouerait quand même, et le modèle écrirait « la recherche n'a pas fonctionné » alors
    que treize moteurs disponibles n'ont jamais été sollicités.
    """
    # Client séquentiel, et non indexé par page : la relance redemande la page 1, donc un client
    # qui répond « selon la page » rejouerait éternellement la même charge muette.
    client = ClientSequentiel([_page(muets=[["brave", "CAPTCHA"]]), _page(1, 2)])
    tirage_moteurs = TirageMoteurs()
    reponse = asyncio.run(
        rechercher(
            ParametresRecherche(requete="rtx 5080"),
            client=client,
            tirage_moteurs=tirage_moteurs,
            cache_recherches=CacheRecherches(),
        )
    )

    assert len(reponse.resultats) == 2
    assert client.moteurs_demandes[0] != client.moteurs_demandes[-1], "relancé sur le même lot"


def test_pagination_bornee_a_deux_pages() -> None:
    """Chaque page apporte du neuf : la borne, et rien d'autre, doit arrêter la boucle."""
    charges = [_page(1, 2), _page(3, 4), _page(5, 6), _page(7, 8)]
    reponse, client = _lancer(charges, nombre=50)

    assert client.pages_demandees == [1, 2]
    assert len(reponse.resultats) == 4
    assert reponse.pages_interrogees == 2


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
