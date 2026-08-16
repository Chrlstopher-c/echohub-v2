"""Domaine `fichiers` — magasin unique des fichiers de conversation.

Un fichier joint par l'utilisateur et un fichier produit par le modèle passent par le MÊME
mécanisme, distingués par `origine`. Les octets ne vivent jamais en base : la table
`fichiers_conversation` (schéma additif, créé par `backend.chat.depot`) ne porte que des
références ; le contenu vit sur le disque, sous `Settings.data_home`.

Interface publique : les autres domaines n'importent que ce qui est exporté ici, jamais
`backend.fichiers.depot` ni `backend.fichiers.stockage` directement.

Assemblage type dans `main.py` :

    application.include_router(fichiers.routeur, prefix="/api")

Branchement de la suppression : `backend.chat.depot.supprimer_conversation` appelle
`supprimer_dossier_conversation` (import différé, pour éviter un cycle avec `backend.chat`, dont
ce domaine dépend pour vérifier l'existence d'une conversation avant tout dépôt).
"""

from backend.fichiers.erreurs import (
    FichierIntrouvable,
    FichierTropVolumineux,
    QuotaConversationDepasse,
    TypeMimeRefuse,
)
from backend.fichiers.modeles import FichierConversation, OrigineFichier
from backend.fichiers.politique import TAILLE_MAX_CUMULEE_OCTETS, TAILLE_MAX_FICHIER_OCTETS
from backend.fichiers.routes import routeur
from backend.fichiers.service import (
    chemin_disque,
    deposer_fichier,
    lier_fichiers_au_message,
    lire_fichier,
    pieces_pour_messages,
    resoudre_reference,
)
from backend.fichiers.stockage import supprimer_dossier_conversation

__all__ = [
    # Structures
    "FichierConversation",
    "OrigineFichier",
    # Erreurs
    "FichierIntrouvable",
    "FichierTropVolumineux",
    "QuotaConversationDepasse",
    "TypeMimeRefuse",
    # Quotas
    "TAILLE_MAX_FICHIER_OCTETS",
    "TAILLE_MAX_CUMULEE_OCTETS",
    # Opérations
    "deposer_fichier",
    "lire_fichier",
    "resoudre_reference",
    "chemin_disque",
    "lier_fichiers_au_message",
    "pieces_pour_messages",
    "supprimer_dossier_conversation",
    # API HTTP
    "routeur",
]
