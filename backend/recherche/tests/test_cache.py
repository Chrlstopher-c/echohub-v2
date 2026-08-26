"""Ce que ces tests prouvent : une répétition ne coûte rien, une panne n'est jamais mémorisée."""

from __future__ import annotations

from backend.recherche.cache import CacheRecherches
from backend.recherche.modeles import (
    LANGUE_TOUTES,
    CategorieRecherche,
    ParametresRecherche,
    ReponseRecherche,
    ResultatRecherche,
)

_UN_RESULTAT = (ResultatRecherche(titre="T", url="https://exemple.test/a"),)


def _reponse(resultats: tuple[ResultatRecherche, ...] = _UN_RESULTAT) -> ReponseRecherche:
    return ReponseRecherche(
        requete="ressorts",
        categorie=CategorieRecherche.GENERAL,
        langue=LANGUE_TOUTES,
        resultats=resultats,
    )


def test_une_requete_identique_est_servie_sans_reseau() -> None:
    cache = CacheRecherches()
    parametres = ParametresRecherche(requete="ressorts")
    cache.ecrire(parametres, _reponse(), horloge=0.0)
    assert cache.lire(parametres, horloge=1.0) is not None


def test_la_normalisation_absorbe_casse_et_espaces() -> None:
    """Un modèle ne réécrit pas deux fois la même chaîne au caractère près — c'était le cas mesuré."""
    cache = CacheRecherches()
    cache.ecrire(ParametresRecherche(requete="Ressorts  Auto"), _reponse(), horloge=0.0)
    assert cache.lire(ParametresRecherche(requete="ressorts auto"), horloge=1.0) is not None


def test_un_nombre_de_resultats_different_est_une_autre_recherche() -> None:
    """Une demande de 30 ne peut pas être servie par une réponse tronquée à 10."""
    cache = CacheRecherches()
    cache.ecrire(ParametresRecherche(requete="r", nombre_resultats=10), _reponse(), horloge=0.0)
    assert cache.lire(ParametresRecherche(requete="r", nombre_resultats=30), horloge=1.0) is None


def test_une_entree_expiree_repart_au_reseau() -> None:
    cache = CacheRecherches(duree_vie_s=10.0)
    parametres = ParametresRecherche(requete="r")
    cache.ecrire(parametres, _reponse(), horloge=0.0)
    assert cache.lire(parametres, horloge=11.0) is None


def test_une_reponse_vide_n_est_pas_memorisee() -> None:
    """Mettre une panne en cache la figerait un quart d'heure : l'inverse exact du but."""
    cache = CacheRecherches()
    parametres = ParametresRecherche(requete="r")
    cache.ecrire(parametres, _reponse(()), horloge=0.0)
    assert cache.lire(parametres, horloge=1.0) is None


def test_la_capacite_est_bornee_et_evince_le_plus_ancien() -> None:
    cache = CacheRecherches(taille_max=2)
    for indice in range(3):
        cache.ecrire(ParametresRecherche(requete=f"r{indice}"), _reponse(), horloge=float(indice))
    assert cache.taille() == 2
    assert cache.lire(ParametresRecherche(requete="r0"), horloge=4.0) is None
    assert cache.lire(ParametresRecherche(requete="r2"), horloge=4.0) is not None
