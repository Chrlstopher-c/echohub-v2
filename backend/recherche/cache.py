"""Cache de recherches — le levier qui coûte le moins et qui rend le plus.

CE QU'IL RÉPARE, MESURÉ. Le 2026-08-26, un modèle a émis SIX appels `recherche_web` identiques
d'affilée dans une même réponse. Chacun est parti vers SearXNG, qui l'a distribué à tous ses
moteurs actifs, sur plusieurs pages : la même question a coûté des dizaines de requêtes sortantes
et a contribué à faire suspendre le pool. Le sixième appel ne pouvait rien apprendre que le premier
n'avait pas déjà dit.

Un agent revient sur ses pas — il reformule à l'identique, il vérifie, il boucle. C'est son mode de
fonctionnement normal, pas un défaut à corriger dans le modèle. Le harnais doit l'absorber.

CE QUE CE CACHE N'EST PAS. Il ne remplace pas la recherche : la durée de vie est courte, et une
entrée expirée repart au réseau. Il ne mémorise que des SUCCÈS — une panne mise en cache serait une
panne rejouée alors que le service est peut-être revenu. Et il est en mémoire du processus, donc
perdu au redémarrage : personne n'a besoin qu'une recherche d'hier survive à un `docker restart`.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Final

from loguru import logger

from backend.recherche.modeles import ParametresRecherche, ReponseRecherche

# Quinze minutes : assez long pour couvrir une conversation entière, assez court pour qu'une
# actualité ne soit pas servie périmée. Le web ne bouge pas en un quart d'heure sur les requêtes
# qu'un agent répète.
DUREE_VIE_S: Final = 900.0

# Plafond d'entrées. Une réponse pèse quelques dizaines de kilo-octets au plus ; deux cent
# cinquante-six tiennent largement en mémoire, et la borne existe pour qu'un processus de longue
# durée ne grossisse pas indéfiniment — pas parce que la mémoire manque.
TAILLE_MAX: Final = 256


def _cle(parametres: ParametresRecherche) -> tuple[str, str, str, int]:
    """Clé d'identité d'une recherche.

    La requête est normalisée (casse, espaces) parce qu'un modèle réécrit rarement deux fois la
    même chaîne au caractère près. Le nombre de résultats EN FAIT partie : une demande de 30
    résultats ne peut pas être servie par une réponse tronquée à 10.
    """
    requete = " ".join(parametres.requete.lower().split())
    return (requete, parametres.categorie.value, parametres.langue, parametres.nombre_resultats)


class CacheRecherches:
    """Cache à durée de vie et capacité bornées. Ordonné par ancienneté d'écriture."""

    def __init__(self, duree_vie_s: float = DUREE_VIE_S, taille_max: int = TAILLE_MAX) -> None:
        self._duree_vie_s = duree_vie_s
        self._taille_max = taille_max
        self._entrees: OrderedDict[tuple[str, str, str, int], tuple[float, ReponseRecherche]] = OrderedDict()

    def lire(self, parametres: ParametresRecherche, *, horloge: float | None = None) -> ReponseRecherche | None:
        """La réponse encore valide pour ces paramètres, ou `None`."""
        maintenant = time.monotonic() if horloge is None else horloge
        cle = _cle(parametres)
        entree = self._entrees.get(cle)
        if entree is None:
            return None
        expire_a, reponse = entree
        if expire_a <= maintenant:
            del self._entrees[cle]
            return None
        logger.info("recherche « {} » servie par le cache ({} résultat(s), aucun appel réseau)",
                    parametres.requete, len(reponse.resultats))
        return reponse

    def ecrire(self, parametres: ParametresRecherche, reponse: ReponseRecherche,
               *, horloge: float | None = None) -> None:
        """Mémorise un succès. Une réponse vide n'est PAS un succès et n'est pas mémorisée.

        Zéro résultat peut venir d'un pool momentanément épuisé autant que d'une requête sans
        réponse. Le mettre en cache figerait la panne pour un quart d'heure — exactement l'inverse
        du but.
        """
        if not reponse.resultats:
            return
        maintenant = time.monotonic() if horloge is None else horloge
        cle = _cle(parametres)
        self._entrees.pop(cle, None)
        self._entrees[cle] = (maintenant + self._duree_vie_s, reponse)
        while len(self._entrees) > self._taille_max:
            self._entrees.popitem(last=False)

    def vider(self) -> None:
        """Utilisé par les tests, et par un appelant qui veut forcer un aller-retour réseau."""
        self._entrees.clear()

    def taille(self) -> int:
        return len(self._entrees)


# Instance de processus, comme le tirage de moteurs : partagée par toutes les recherches, atteinte
# uniquement par la fonction ci-dessous.
_CACHE = CacheRecherches()


def cache() -> CacheRecherches:
    """Le cache partagé par toutes les recherches de ce processus."""
    return _CACHE


__all__ = ["DUREE_VIE_S", "TAILLE_MAX", "CacheRecherches", "cache"]
