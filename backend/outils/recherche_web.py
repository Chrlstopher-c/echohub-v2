"""Outil de recherche web — le premier du harnais, adossé à SearXNG en local.

Ce module traduit dans les deux sens : un appel du modèle vers le domaine `recherche`, puis les
résultats vers un texte que le modèle sait lire. Il ne contient aucune logique de recherche ; tout
ce qui touche à SearXNG appartient au domaine `recherche` et n'est vu qu'à travers son interface.

Le texte rendu porte les URL. C'est délibéré : sans elles, le modèle cite de mémoire et invente des
sources. Avec elles, l'utilisateur peut vérifier — et c'est le seul garde-fou réel contre une
réponse plausible et fausse.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from backend.outils.contrat import DescriptionOutil, Outil
from backend.recherche import CategorieRecherche, ParametresRecherche, rechercher

NOM = "recherche_web"

# Au-delà, le résultat mange le contexte sans rien apporter : les extraits SearXNG sont courts et
# les premiers résultats portent l'essentiel. Borne assumée, pas une limite du moteur.
RESULTATS_MAX = 6

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "requete": {
            "type": "string",
            "description": "Les mots-clés à chercher. Formuler comme dans un moteur de recherche, "
            "pas comme une question complète.",
        },
        "nombre_resultats": {
            "type": "integer",
            "description": f"Nombre de résultats souhaités, de 1 à {RESULTATS_MAX}.",
            "minimum": 1,
            "maximum": RESULTATS_MAX,
        },
    },
    "required": ["requete"],
}

DESCRIPTION = DescriptionOutil(
    nom=NOM,
    description=(
        "Cherche sur le web et rend des résultats réels avec leurs URL. À utiliser dès que la "
        "question porte sur l'actualité, sur des faits postérieurs à l'entraînement, sur des "
        "chiffres précis, ou sur quoi que ce soit qui doive être vérifiable."
    ),
    parametres=_SCHEMA,
)


def _formater(titre: str, url: str, extrait: str | None, rang: int) -> str:
    corps = (extrait or "").strip().replace("\n", " ")
    return f"[{rang}] {titre.strip()}\n{url}\n{corps}" if corps else f"[{rang}] {titre.strip()}\n{url}"


async def executer(arguments: dict[str, Any]) -> str:
    """Exécute la recherche et rend un texte destiné au contexte du modèle.

    Toute erreur est rendue comme texte plutôt que levée : le modèle doit apprendre que la
    recherche a échoué pour le dire à l'utilisateur, au lieu de recevoir un silence qu'il
    comblerait en inventant.
    """
    requete = str(arguments.get("requete", "")).strip()
    if not requete:
        return "Échec : aucune requête fournie. Rappeler l'outil avec des mots-clés."

    demande = arguments.get("nombre_resultats")
    nombre = demande if isinstance(demande, int) and 1 <= demande <= RESULTATS_MAX else RESULTATS_MAX
    try:
        reponse = await rechercher(
            ParametresRecherche(requete=requete, categorie=CategorieRecherche.GENERAL, nombre_resultats=nombre)
        )
    except Exception as exc:  # noqa: BLE001 — frontière : tout échec doit revenir au modèle en texte
        logger.error("Recherche web « {} » échouée : {}", requete, exc)
        return f"Échec de la recherche web : {exc}. Le dire à l'utilisateur plutôt que de répondre de mémoire."

    resultats = list(reponse.resultats)[:nombre]
    if not resultats:
        return f"Aucun résultat pour « {requete} ». Le dire à l'utilisateur ; ne pas inventer de sources."

    lignes = [_formater(r.titre, r.url, r.extrait, i) for i, r in enumerate(resultats, start=1)]
    entete = f"{len(lignes)} résultat(s) pour « {requete} » :"
    return "\n\n".join([entete, *lignes])


OUTIL = Outil(description=DESCRIPTION, executer=executer)
