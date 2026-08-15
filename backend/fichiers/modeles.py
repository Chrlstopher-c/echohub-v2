"""Structures du domaine `fichiers` — fichiers de conversation, pièces jointes ou artefacts.

Une seule forme pour les deux origines : ce qui distingue un fichier joint par l'utilisateur d'un
fichier produit par le modèle est uniquement `origine`. Les octets ne vivent jamais ici —
`chemin_relatif` est une référence vers le disque (`backend/fichiers/stockage.py`), jamais un
contenu encodé. `nom_affiche` conserve le nom fourni par l'utilisateur ou le modèle pour l'affichage
uniquement : il ne sert ni à décider du type MIME, ni de l'extension écrite sur le disque — ces deux
décisions viennent du type MIME validé (`backend/fichiers/politique.py`), jamais du nom.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

OrigineFichier = Literal["utilisateur", "modele"]


class FichierConversation(BaseModel):
    """Ligne de `fichiers_conversation` — une référence, jamais un contenu."""

    id: str
    conversation_id: str
    message_id: str | None = None
    origine: OrigineFichier
    nom_affiche: str
    chemin_relatif: str
    type_mime: str
    taille_octets: int = Field(ge=0)
    empreinte_sha256: str
    cree_le: datetime
