"""Vocabulaire typé du domaine `recherche`.

Règle appliquée sans exception : un champ que SearXNG n'a pas renvoyé vaut `None` ou une séquence
vide, jamais une valeur de remplacement. Un extrait absent n'est pas une chaîne vide « pour faire
propre » — c'est une absence, et l'appelant doit pouvoir la distinguer d'un extrait réellement vide.

Deux structures de réponse cohabitent volontairement :
- `PageRecherche` est ce que SearXNG a rendu pour UNE page. C'est un constat brut, analysé sans
  interprétation ;
- `ReponseRecherche` est le résultat métier après agrégation des pages, dédoublonnage et troncature.
  Elle porte en plus les mesures de l'appel (durée, pages réellement interrogées).

Les séparer évite le piège classique : une structure unique qui prétend décrire à la fois une page
et un agrégat finit par mentir sur l'un des deux.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Final

from pydantic import BaseModel, Field, field_validator

# Catégories SearXNG, valeurs telles qu'attendues par son paramètre `categories`. Ce sont des
# identifiants de protocole : ils ne sont pas traduits, seuls les noms de membres le sont.
class CategorieRecherche(str, Enum):
    """Catégorie interrogée. `GENERAL` couvre le web au sens large."""

    GENERAL = "general"
    ACTUALITES = "news"
    SCIENCE = "science"
    INFORMATIQUE = "it"
    IMAGES = "images"
    VIDEOS = "videos"
    MUSIQUE = "music"
    FICHIERS = "files"


LANGUE_TOUTES: Final = "all"

# `all` (aucun filtre), `auto` (détection par SearXNG), ou un code ISO éventuellement régionalisé.
# Le motif sert deux fois : validation HTTP par FastAPI et validation du modèle. Il ferme surtout
# la porte à l'injection de n'importe quoi dans la chaîne de requête envoyée à SearXNG.
MOTIF_LANGUE: Final = r"^(all|auto|[a-z]{2}(-[A-Za-z]{2})?)$"

LONGUEUR_REQUETE_MAX: Final = 500
NOMBRE_RESULTATS_DEFAUT: Final = 10
NOMBRE_RESULTATS_MAX: Final = 50


def maintenant_utc() -> datetime:
    """Horodatage des mesures. UTC partout, pour que deux mesures restent comparables."""
    return datetime.now(timezone.utc)


class ParametresRecherche(BaseModel):
    """Demande de recherche validée. Seule forme acceptée par le service."""

    requete: str = Field(min_length=1, max_length=LONGUEUR_REQUETE_MAX)
    categorie: CategorieRecherche = CategorieRecherche.GENERAL
    langue: str = Field(default=LANGUE_TOUTES, pattern=MOTIF_LANGUE)
    nombre_resultats: int = Field(default=NOMBRE_RESULTATS_DEFAUT, ge=1, le=NOMBRE_RESULTATS_MAX)

    @field_validator("requete")
    @classmethod
    def _requete_non_vide(cls, valeur: str) -> str:
        """Une requête d'espaces passerait `min_length` et interrogerait tous les moteurs pour rien."""
        nettoyee = valeur.strip()
        if not nettoyee:
            raise ValueError("La requête ne peut pas être vide.")
        return nettoyee


class ResultatRecherche(BaseModel):
    """Un résultat exploitable : il a au minimum un titre et une URL ouvrable."""

    titre: str
    url: str
    # `content` chez SearXNG. Certains moteurs n'en fournissent aucun : l'absence est conservée.
    extrait: str | None = None
    # Moteur ayant fourni la ligne, et l'ensemble des moteurs qui l'ont proposée après fusion.
    moteur: str | None = None
    moteurs: tuple[str, ...] = ()
    # Score de fusion SearXNG. Non comparable d'une requête à l'autre : c'est un rang, pas une note.
    score: float | None = None
    publie_le: datetime | None = None


class MoteurMuet(BaseModel):
    """Moteur qui n'a pas répondu pendant la recherche. Sa raison est parfois absente."""

    moteur: str
    raison: str | None = None


class PageRecherche(BaseModel):
    """Une page de résultats telle que SearXNG l'a rendue, analysée sans interprétation."""

    resultats: tuple[ResultatRecherche, ...] = ()
    # `answers` : réponse directe (calcul, définition, conversion) quand un moteur en produit une.
    reponses_directes: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    moteurs_muets: tuple[MoteurMuet, ...] = ()
    # `number_of_results` vaut très souvent 0 alors que des résultats existent : ce zéro n'est pas
    # une mesure, il est converti en `None` à l'analyse.
    nombre_annonce: int | None = None


class ReponseRecherche(BaseModel):
    """Résultat métier d'une recherche : ce que le domaine expose hors de ses frontières."""

    requete: str
    categorie: CategorieRecherche
    langue: str
    resultats: tuple[ResultatRecherche, ...] = ()
    reponses_directes: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    # Exposé volontairement : une réponse partielle doit se voir. Des résultats accompagnés de
    # moteurs muets sont une réponse dégradée, pas une réponse complète.
    moteurs_muets: tuple[MoteurMuet, ...] = ()
    nombre_annonce: int | None = None
    pages_interrogees: int = Field(default=0, ge=0)
    duree_ms: float | None = None
    interroge_le: datetime = Field(default_factory=maintenant_utc)


class SanteRecherche(BaseModel):
    """Disponibilité mesurée du service SearXNG, à l'instant de l'appel."""

    disponible: bool
    url: str
    latence_ms: float | None = None
    statut_http: int | None = None
    # Ce qui a été mesuré, en clair : code inattendu, erreur réseau, ou bilan de la sonde complète.
    detail: str = ""
    verifie_le: datetime = Field(default_factory=maintenant_utc)
