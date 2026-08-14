"""Analyse de la charge JSON de SearXNG — module pur, sans réseau ni état.

Pourquoi le séparer du client : c'est ici que se trouve tout le risque de régression (le schéma
JSON de SearXNG a déjà changé de forme entre versions), et c'est la seule partie testable sans
service en face. Le client, lui, ne fait que du transport.

Principe de lecture : **rien n'est supposé présent**. Chaque champ est vérifié pour son type avant
d'être retenu ; une valeur absente, vide ou d'un type inattendu devient `None` ou une séquence vide.
Aucune valeur de remplacement n'est inventée, aucune ligne n'est complétée par déduction.

Une seule ligne est écartée : celle qui n'a ni URL ni titre exploitables. Elle ne peut être ni
ouverte ni affichée — la garder reviendrait à faire passer un artefact d'analyse pour un résultat.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from backend.recherche.modeles import MoteurMuet, PageRecherche, ResultatRecherche


def analyser_page(charge: dict[str, Any]) -> PageRecherche:
    """Convertit une réponse JSON de SearXNG en constat typé. Ne lève jamais : elle écarte."""
    bruts = charge.get("results")
    bruts = bruts if isinstance(bruts, list) else []
    resultats = tuple(r for brut in bruts if (r := _analyser_resultat(brut)) is not None)

    ecartes = len(bruts) - len(resultats)
    if ecartes:
        logger.debug("{} entrée(s) SearXNG écartée(s) : ni URL ni titre exploitables", ecartes)

    return PageRecherche(
        resultats=resultats,
        reponses_directes=_analyser_reponses_directes(charge.get("answers")),
        suggestions=_liste_de_textes(charge.get("suggestions")),
        moteurs_muets=_analyser_moteurs_muets(charge.get("unresponsive_engines")),
        nombre_annonce=_analyser_nombre_annonce(charge.get("number_of_results")),
    )


def _analyser_resultat(brut: object) -> ResultatRecherche | None:
    """Une entrée de `results`. Rend `None` si elle n'est pas exploitable telle quelle."""
    if not isinstance(brut, dict):
        return None
    url = _texte(brut.get("url"))
    titre = _texte(brut.get("title"))
    if url is None or titre is None:
        return None
    return ResultatRecherche(
        titre=titre,
        url=url,
        extrait=_texte(brut.get("content")),
        moteur=_texte(brut.get("engine")),
        moteurs=_liste_de_textes(brut.get("engines")),
        score=_nombre(brut.get("score")),
        publie_le=_analyser_date(brut.get("publishedDate")),
    )


def _analyser_reponses_directes(valeur: object) -> tuple[str, ...]:
    """`answers` a changé de forme selon les versions : liste de chaînes, puis liste d'objets.

    Les deux formes sont lues plutôt que d'imposer une version de SearXNG — le conteneur suit
    `latest`, et une réponse directe perdue en silence serait invisible à l'usage.
    """
    if not isinstance(valeur, list):
        return ()
    reponses: list[str] = []
    for element in valeur:
        texte = _texte(element)
        if texte is None and isinstance(element, dict):
            texte = _texte(element.get("answer"))
        if texte is not None:
            reponses.append(texte)
    return tuple(reponses)


def _analyser_moteurs_muets(valeur: object) -> tuple[MoteurMuet, ...]:
    """`unresponsive_engines` : couples `[moteur, raison]`, parfois un troisième élément.

    Cette information décide de la suite : sans résultat ET avec des moteurs muets, le service
    lève une erreur au lieu de rendre une liste vide. Elle doit donc être lue sans approximation.
    """
    if not isinstance(valeur, list):
        return ()
    muets: list[MoteurMuet] = []
    for element in valeur:
        if isinstance(element, str):
            nom, raison = _texte(element), None
        elif isinstance(element, (list, tuple)) and element:
            nom = _texte(element[0])
            raison = _texte(element[1]) if len(element) > 1 else None
        else:
            continue
        if nom is not None:
            muets.append(MoteurMuet(moteur=nom, raison=raison))
    return tuple(muets)


def _analyser_nombre_annonce(valeur: object) -> int | None:
    """`number_of_results` vaut souvent 0 alors que des résultats existent : ce 0 n'est pas une mesure."""
    nombre = _nombre(valeur)
    if nombre is None or nombre <= 0:
        return None
    return int(nombre)


def _analyser_date(valeur: object) -> datetime | None:
    """`publishedDate` n'est ni garanti présent ni garanti ISO : illisible vaut `None`, jamais « maintenant »."""
    texte = _texte(valeur)
    if texte is None:
        return None
    # `fromisoformat` de Python 3.10 ne connaît pas le suffixe Z, largement utilisé par les moteurs.
    normalise = f"{texte[:-1]}+00:00" if texte.endswith("Z") else texte
    try:
        return datetime.fromisoformat(normalise)
    except ValueError:
        logger.debug("Date de publication illisible, ignorée : {}", texte)
        return None


def _liste_de_textes(valeur: object) -> tuple[str, ...]:
    """Liste de chaînes non vides ; tout élément d'un autre type est écarté sans bruit."""
    if not isinstance(valeur, list):
        return ()
    return tuple(t for element in valeur if (t := _texte(element)) is not None)


def _texte(valeur: object) -> str | None:
    """Chaîne non vide, ou `None`. Une chaîne vide n'est pas une mesure, c'est une absence."""
    if not isinstance(valeur, str):
        return None
    nettoye = valeur.strip()
    return nettoye or None


def _nombre(valeur: object) -> float | None:
    """Nombre réel, ou `None`. `bool` est exclu explicitement : en Python il passe pour un `int`."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    return float(valeur)
