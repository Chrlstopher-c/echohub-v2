"""Erreurs métier du domaine `recherche`.

Elles héritent de `EchoHubError` : la couche API les traduit en réponse HTTP via `statut_http` et
`to_dict()`, sans réécrire de table de correspondance.

La distinction entre les deux n'est pas cosmétique, elle dit à l'utilisateur quoi faire :
- `RechercheIndisponible` → le service n'a pas été atteint. C'est l'infrastructure qu'il faut
  regarder (conteneur éteint, réseau interne, URL de configuration).
- `RechercheEchouee` → le service a été atteint mais sa réponse est inutilisable. C'est SearXNG
  lui-même ou sa configuration qu'il faut regarder.

Aucune des deux n'est remplaçable par une liste vide. Rendre `[]` sur une panne ferait passer une
défaillance pour un constat — exactement le défaut que la v2 corrige.
"""

from __future__ import annotations

from backend.core import EchoHubError


class RechercheIndisponible(EchoHubError):
    """SearXNG n'a pas répondu : conteneur arrêté, réseau interne coupé, ou délai dépassé."""

    code = "recherche_indisponible"
    statut_http = 503
    remediation_defaut = (
        "Vérifier que le service searxng tourne (docker compose ps) et que SEARXNG_URL pointe dessus."
    )


class RechercheEchouee(EchoHubError):
    """SearXNG a répondu, mais sa réponse est inexploitable ou aucun moteur n'a rendu de résultat."""

    code = "recherche_echouee"
    statut_http = 502
    remediation_defaut = (
        "Consulter les journaux du conteneur searxng : format JSON désactivé, ou moteurs tous en échec."
    )
