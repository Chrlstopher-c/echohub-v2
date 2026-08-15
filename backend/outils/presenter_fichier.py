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

from backend.fichiers import FichierIntrouvable, lire_fichier
from backend.outils.contrat import ContexteExecution, DescriptionOutil, Outil

NOM = "presenter_fichier"

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fichier_id": {
            "type": "string",
            "description": "Identifiant du fichier à présenter — celui rendu par `executer_python` "
            "après avoir produit un fichier, ou celui d'une pièce jointe de cette conversation.",
        },
    },
    "required": ["fichier_id"],
}

DESCRIPTION = DescriptionOutil(
    nom=NOM,
    description=(
        "Affiche, dans le fil de la conversation, un fichier qui existe déjà (produit par "
        "`executer_python`, ou joint par l'utilisateur) sous forme de carte cliquable que "
        "l'utilisateur peut ouvrir pour en voir le code source ou un aperçu. Utiliser cet outil "
        "après avoir produit ou reçu un fichier qui mérite d'être montré — pas pour un résultat "
        "purement textuel, qui n'a pas besoin d'être présenté."
    ),
    parametres=_SCHEMA,
)


async def executer(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
    """Vérifie que le fichier appartient à CETTE conversation, rend sa référence en JSON.

    Un identifiant d'une autre conversation est refusé exactement comme s'il n'existait pas : le
    rendre visible ici fuiterait un fichier vers une conversation qui n'y a pas droit — même
    discipline que `service.lier_fichiers_au_message`.
    """
    fichier_id = str(arguments.get("fichier_id", "")).strip()
    if not fichier_id:
        return "Échec : aucun « fichier_id » fourni. Rappeler l'outil avec cet argument."
    try:
        fichier = lire_fichier(fichier_id)
    except FichierIntrouvable:
        return f"Échec : aucun fichier « {fichier_id} » n'existe."
    if fichier.conversation_id != contexte.conversation_id:
        logger.warning("presenter_fichier : {} hors de la conversation {}", fichier_id, contexte.conversation_id)
        return f"Échec : aucun fichier « {fichier_id} » n'existe."
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
