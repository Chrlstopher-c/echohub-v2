"""Choix des moteurs interrogés — la pièce qui empêche le rate-limit, mesurée le 2026-08-26.

CE QUI TOMBAIT, ET POURQUOI. Le 2026-08-26, trois recherches rapprochées d'un agent ont suspendu
EN MÊME TEMPS les trois seuls moteurs `general` actifs du catalogue par défaut :

    brave : too many requests · duckduckgo : CAPTCHA · startpage : Suspended: CAPTCHA

Le modèle a alors écrit sa page « avec ce qu'il connaît du secteur » : l'invention que le socle
interdit, provoquée par le harnais. Trois causes se cumulaient, toutes vérifiées :

1. **Quatre moteurs seulement** répondaient en catégorie `general` (brave, duckduckgo, startpage,
   google — ce dernier muet sans même le dire). Le catalogue en compte pourtant 280.
2. **SearXNG interroge TOUS les moteurs actifs à chaque appel.** Une recherche n'est pas une
   requête sortante, c'en est une PAR moteur.
3. **La pagination multipliait le tout** : `_PAGES_MAX` pages, donc autant d'appels à chaque
   moteur, pour UNE recherche.

Mesure de la fragilité, faite ici : `yep` a rendu 20 résultats au premier appel et « access denied »
au troisième. Le budget d'un moteur scrapé se compte en unités, pas en dizaines — et le service en
consommait trois par recherche.

CE QUI EST FAIT. Le paramètre `engines=` de SearXNG outrepasse le `disabled` du catalogue : mesuré,
baidu / yandex / seznam / gmx sont désactivés et répondent quand même lorsqu'ils sont nommés. Le
pool vit donc ICI, en Python testable, et non dans `settings.yml` — où une liste `engines` risque
d'empêcher le conteneur de démarrer, et où rien ne se teste.

Deux mécanismes, et c'est tout :

- **Rotation** stricte à tour de rôle sur le pool. Chaque appel prend les k suivants, jamais les k
  premiers. Un tirage aléatoire, ou un ordre fixe, servirait toujours les mêmes en tête : la leçon
  est déjà écrite ailleurs dans ce projet — face à une ressource rationnée, l'inéquité d'un ordre
  stable n'est pas improbable, elle est certaine.
- **Mise à l'écart** de ce que SearXNG a signalé muet. Réinterroger un moteur qui vient de répondre
  CAPTCHA ne rend rien ET prolonge sa suspension : c'est la seule action strictement perdante.
"""

from __future__ import annotations

import time
from typing import Final

from loguru import logger

from backend.recherche.modeles import MoteurMuet

# Pool `general`, mesuré le 2026-08-26 sur l'instance de la pile (résultats rendus pour une requête
# francophone, moteur nommé seul). L'ordre est celui de la rotation, entrelacé volontairement : deux
# moteurs consécutifs ne partagent ni index ni opérateur, pour qu'un tour n'interroge jamais quatre
# façades du même fournisseur.
#
#   gabanza 30 · yep 20 · yandex 15 · naver 15 · bing 10 · duckduckgo web 10 · privacywall 10
#   seznam 10 · baidu 10 · gmx 10 · zapmeta 9 · boardreader 8 · 360search 6 · fynd 4
#
# Écartés parce que mesurés à zéro résultat SANS être muets — ils répondent, ils n'ont rien :
# mojeek, google, crowdview, wiby, searchmysite, resulthunter, ayo, reloado.
# Écartés parce que refusant l'accès : qwant, presearch, dogpile, fireball, infospace, sogou,
# searchtoday, tusksearch, yahoo (erreur de protocole), quark (plantage).
POOL_GENERAL: Final[tuple[str, ...]] = (
    "gabanza",
    "yandex",
    "bing",
    "seznam",
    "yep",
    "naver",
    "duckduckgo web",
    "baidu",
    "privacywall",
    "gmx",
    "zapmeta",
    "360search",
    "boardreader",
    "fynd",
    # Les trois d'origine restent dans le pool, en fin de rotation : ils sont excellents quand ils
    # répondent. Les retirer serait remplacer une fragilité par une autre.
    "brave",
    "duckduckgo",
    "startpage",
)

# Nombre de moteurs interrogés par appel. Quatre suffisent à fusionner 20-40 résultats quand ils
# répondent, et divisent par quatre la charge vue par chacun sur un pool de dix-sept.
MOTEURS_PAR_APPEL_DEFAUT: Final = 4

# Deux durées, parce que deux natures d'échec. Un blocage est une décision du moteur, qui dure ;
# un timeout est un aléa, qui ne dit rien de notre légitimité.
ECART_BLOCAGE_S: Final = 1800.0
ECART_ALEA_S: Final = 300.0

# Fragments lus dans `unresponsive_engines`. SearXNG ne normalise pas ces messages — ils viennent
# du moteur — donc la reconnaissance se fait sur le texte, en minuscules, par inclusion.
_SIGNES_BLOCAGE: Final[tuple[str, ...]] = (
    "captcha",
    "too many requests",
    "access denied",
    "suspended",
    "rate limit",
    "forbidden",
    "429",
)


class TirageMoteurs:
    """Rotation à tour de rôle sur un pool, avec mise à l'écart des moteurs qui ont refusé.

    L'état est mutable et partagé par toutes les recherches du processus : c'est voulu, et c'est le
    seul moyen qu'une rotation ait un sens. Aucun verrou : chaque méthode est synchrone et sans
    `await`, donc indivisible du point de vue de la boucle d'événements.
    """

    def __init__(self, pool: tuple[str, ...] = POOL_GENERAL) -> None:
        if not pool:
            raise ValueError("Le pool de moteurs ne peut pas être vide.")
        self._pool = pool
        self._curseur = 0
        self._ecartes: dict[str, float] = {}

    def choisir(self, nombre: int = MOTEURS_PAR_APPEL_DEFAUT, *, horloge: float | None = None) -> tuple[str, ...]:
        """Les `nombre` prochains moteurs disponibles, en avançant le curseur d'autant.

        Parcourt au plus un tour complet : si tout le pool est à l'écart, rend le tour entier plutôt
        qu'une liste vide — une recherche qui part vers des moteurs suspendus vaut mieux qu'une
        recherche qui ne part pas, et SearXNG dira lui-même qu'ils sont muets.
        """
        maintenant = time.monotonic() if horloge is None else horloge
        disponibles = [nom for nom in self._pool if not self._est_ecarte(nom, maintenant)]
        if not disponibles:
            logger.warning("Tous les moteurs du pool sont à l'écart : le tour complet est tenté.")
            disponibles = list(self._pool)
        voulus = max(1, min(nombre, len(disponibles)))
        depart = self._curseur % len(disponibles)
        choisis = tuple(disponibles[(depart + decalage) % len(disponibles)] for decalage in range(voulus))
        self._curseur = depart + voulus
        return choisis

    def signaler_muets(self, muets: tuple[MoteurMuet, ...], *, horloge: float | None = None) -> None:
        """Met à l'écart ce que SearXNG a signalé, pour une durée qui dépend de la raison."""
        maintenant = time.monotonic() if horloge is None else horloge
        for muet in muets:
            raison = (muet.raison or "").lower()
            bloque = any(signe in raison for signe in _SIGNES_BLOCAGE)
            duree = ECART_BLOCAGE_S if bloque else ECART_ALEA_S
            self._ecartes[muet.moteur] = maintenant + duree
            logger.info(
                "Moteur « {} » écarté {:.0f} min ({}) : {}",
                muet.moteur, duree / 60, "blocage" if bloque else "aléa", muet.raison or "sans raison",
            )

    def etat(self, *, horloge: float | None = None) -> dict[str, float]:
        """Moteurs actuellement à l'écart et secondes restantes — pour la sonde et le diagnostic."""
        maintenant = time.monotonic() if horloge is None else horloge
        return {
            nom: round(fin - maintenant, 1)
            for nom, fin in sorted(self._ecartes.items())
            if fin > maintenant
        }

    def disponibles(self, *, horloge: float | None = None) -> int:
        maintenant = time.monotonic() if horloge is None else horloge
        return sum(1 for nom in self._pool if not self._est_ecarte(nom, maintenant))

    def _est_ecarte(self, nom: str, maintenant: float) -> bool:
        fin = self._ecartes.get(nom)
        if fin is None:
            return False
        if fin <= maintenant:
            # Purge à la lecture : sans elle, un processus de longue durée accumulerait une entrée
            # par moteur jamais relue.
            del self._ecartes[nom]
            return False
        return True


# Instance de processus, explicite et nommée. Elle n'est pas un global implicite : rien ne la
# manipule hors de ce module, et le service la reçoit par appel de fonction.
_TIRAGE = TirageMoteurs()


def tirage() -> TirageMoteurs:
    """Le tirage partagé par toutes les recherches de ce processus."""
    return _TIRAGE


__all__ = [
    "ECART_ALEA_S",
    "ECART_BLOCAGE_S",
    "MOTEURS_PAR_APPEL_DEFAUT",
    "POOL_GENERAL",
    "TirageMoteurs",
    "tirage",
]
