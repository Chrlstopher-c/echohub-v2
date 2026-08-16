"""Outil `presenter_fichier` — le modèle désigne un fichier, l'utilisateur le voit dans le fil.

Suit le contrat commun (`backend/outils/contrat.py`) : reçoit des arguments validés et le
`ContexteExecution` de l'appelant, rend un texte destiné à repartir dans le contexte du modèle —
ici un JSON compact que le frontend sait reconnaître et transformer en carte d'artefact cliquable
(`frontend/src/chat/artefacts/detection.ts`).

Aucun octet ne traverse cet outil : la référence existe déjà dans le magasin (`backend.fichiers`),
déposée soit par une pièce jointe de l'utilisateur, soit par le balayage du bac après
`executer_python` (`balayage_bac.py`). Cet outil ne fait que la DÉSIGNER pour l'affichage — c'est
la seule chose qu'« un outil de présentation » doit faire (plan d'exécution, lot L3).
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from backend.fichiers import FichierIntrouvable, resoudre_reference
from backend.outils.contrat import ContexteExecution, DescriptionOutil, Outil

NOM = "presenter_fichier"

# Descriptions et schémas EN ANGLAIS : ils sont rendus tels quels dans le gabarit du modèle, à côté
# d'exemples d'appel eux-mêmes anglais. C'est le texte qui décide de la qualité de l'appel émis.
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fichier_id": {
            "type": "string",
            "description": (
                "The file to show. Required — a call without it does nothing. Give EITHER the id "
                "returned by `executer_python` (like `afaaa20c-65a9-…`) OR the file name as it was "
                "produced (`hello.py`, `chart.png`). Both work; the name is enough for a file just "
                "created in this conversation."
            ),
        },
    },
    "required": ["fichier_id"],
}

DESCRIPTION = DescriptionOutil(
    nom=NOM,
    description=(
        "Shows an EXISTING file in the conversation as a clickable card the user can open to read "
        "its source or see a preview. The file must already exist — produced by `executer_python` "
        "or attached by the user; this tool displays, it never creates. Use it after producing or "
        "receiving a file worth showing, not for a purely textual result."
    ),
    parametres=_SCHEMA,
)


async def executer(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
    """Résout la référence DANS cette conversation, rend la référence du fichier en JSON.

    La résolution est déléguée au domaine `fichiers`, qui accepte l'identifiant comme le nom
    affiché : un modèle désigne spontanément « hello.py », pas l'UUID qu'on lui a rendu. Elle
    borne la recherche à la conversation courante, donc un identifiant étranger reste introuvable
    — le rendre visible ici fuiterait un fichier vers une conversation qui n'y a pas droit, même
    discipline que `service.lier_fichiers_au_message`.
    """
    reference = str(arguments.get("fichier_id", "")).strip()
    if not reference:
        return "Échec : aucun « fichier_id » fourni. Rappeler l'outil avec le nom ou l'identifiant du fichier."
    try:
        fichier = resoudre_reference(contexte.conversation_id, reference)
    except FichierIntrouvable:
        logger.warning("presenter_fichier : « {} » introuvable dans {}", reference, contexte.conversation_id)
        return (
            f"Échec : aucun fichier « {reference} » dans cette conversation. "
            "Les fichiers disponibles sont ceux produits par `executer_python` ou joints par "
            "l'utilisateur ; un fichier écrit dans le bac n'existe qu'une fois l'exécution terminée."
        )
    return json.dumps(
        {
            "fichier_id": fichier.id,
            "nom_affiche": fichier.nom_affiche,
            "type_mime": fichier.type_mime,
            "taille_octets": fichier.taille_octets,
            # Le frontend s'en sert pour savoir si le texte des limites du bac à sable (plan
            # d'exécution, 2.6) a un sens à côté de cet artefact : une pièce jointe utilisateur n'a
            # jamais traversé le bac confiné, l'afficher là serait un texte hors sujet.
            "origine": fichier.origine,
        }
    )


OUTIL = Outil(description=DESCRIPTION, executer=executer)

__all__ = ["OUTIL"]
