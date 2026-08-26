"""Domaine `recherche` — recherche web locale via SearXNG.

Ce domaine n'embarque aucun moteur : il délègue à une instance SearXNG qui tourne dans la pile
Docker, sur le réseau interne (`http://searxng:8080`), sans aucun port publié vers l'extérieur.
C'est ce qui rend la fonction souveraine — aucune clé d'API, aucun compte, aucune requête sortante
qui parte du navigateur de l'utilisateur.

Interface publique du domaine. Les autres domaines et la couche d'assemblage n'importent que ce qui
est exporté ici ; `service`, `analyse` et `client_searxng` sont des internes.

    from backend.recherche import ParametresRecherche, rechercher, routeur

Deux points de conception à connaître avant d'utiliser le domaine :

- **Une panne ne se déguise jamais en résultat vide.** Service injoignable → `RechercheIndisponible`.
  Réponse illisible, ou aucun moteur n'ayant répondu → `RechercheEchouee`. Une liste vide signifie
  uniquement que les moteurs ont répondu et n'ont rien trouvé.
- **Le nombre de résultats est un plafond, pas une promesse.** SearXNG rend ce que les moteurs ont
  fusionné ; le service pagine (borné) puis tronque, mais ne complète jamais.

L'URL et le délai du service se lisent dans `backend.core.get_settings()` (`SEARXNG_URL`,
`SEARXNG_TIMEOUT_S`) — rien n'est codé en dur dans ce domaine.
"""

from backend.recherche.api import routeur
from backend.recherche.cache import CacheRecherches, cache
from backend.recherche.client_searxng import ClientSearxng
from backend.recherche.erreurs import RechercheEchouee, RechercheIndisponible
from backend.recherche.modeles import (
    LANGUE_TOUTES,
    LONGUEUR_REQUETE_MAX,
    MOTIF_LANGUE,
    NOMBRE_RESULTATS_DEFAUT,
    NOMBRE_RESULTATS_MAX,
    CategorieRecherche,
    MoteurMuet,
    PageRecherche,
    ParametresRecherche,
    ReponseRecherche,
    ResultatRecherche,
    SanteRecherche,
)
from backend.recherche.pool_moteurs import POOL_GENERAL, TirageMoteurs, tirage
from backend.recherche.service import construire_client, rechercher, sonder

__all__ = [
    # Routeur HTTP, monté par la couche d'assemblage.
    "routeur",
    # Fonctions du domaine
    "rechercher",
    "sonder",
    "construire_client",
    # Client, exposé pour l'injection (tests, appelants qui pilotent une autre instance)
    "ClientSearxng",
    # Protection contre le rate-limit : rotation des moteurs et cache, injectables comme le client
    "TirageMoteurs",
    "tirage",
    "POOL_GENERAL",
    "CacheRecherches",
    "cache",
    # Modèles typés
    "CategorieRecherche",
    "ParametresRecherche",
    "ResultatRecherche",
    "MoteurMuet",
    "PageRecherche",
    "ReponseRecherche",
    "SanteRecherche",
    # Constantes de validation, partagées avec la couche HTTP
    "LANGUE_TOUTES",
    "MOTIF_LANGUE",
    "LONGUEUR_REQUETE_MAX",
    "NOMBRE_RESULTATS_DEFAUT",
    "NOMBRE_RESULTATS_MAX",
    # Erreurs métier
    "RechercheIndisponible",
    "RechercheEchouee",
]
