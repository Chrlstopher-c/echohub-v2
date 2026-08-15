"""Erreurs propres au domaine `fichiers`.

Dérivent de `EchoHubError` pour hériter du contrat commun (`code`, `statut_http`, `remediation`,
`to_dict`) : la couche API les traduit en réponse HTTP sans table de correspondance dédiée.
"""

from __future__ import annotations

from backend.core import EchoHubError

# Pas d'import de `politique` ici : ce module définit les constantes de quota et lève ces erreurs
# avec un message de remédiation déjà chiffré (voir `politique.verifier_taille_fichier` et
# `verifier_quota_cumule`) — l'importer en retour créerait un cycle.


class FichierIntrouvable(EchoHubError):
    """Le fichier demandé n'existe pas, ou n'existe plus."""

    code = "fichier_introuvable"
    statut_http = 404
    remediation_defaut = "Le fichier a peut-être été supprimé avec sa conversation."


class FichierTropVolumineux(EchoHubError):
    """La taille du fichier envoyé dépasse le plafond par fichier."""

    code = "fichier_trop_volumineux"
    statut_http = 413
    remediation_defaut = "Réduire la taille du fichier."


class QuotaConversationDepasse(EchoHubError):
    """La taille cumulée des fichiers de la conversation dépasserait le plafond."""

    code = "quota_conversation_depasse"
    statut_http = 413
    remediation_defaut = "Supprimer des fichiers de cette conversation avant d'en ajouter."


class TypeMimeRefuse(EchoHubError):
    """Le type MIME déclaré n'est pas dans la liste blanche du domaine.

    Jamais déduit du nom du fichier fourni : ce nom est une entrée non fiable (utilisateur ou
    modèle). Seul le type MIME déclaré, validé contre la liste blanche, est retenu.
    """

    code = "type_mime_refuse"
    statut_http = 415
    remediation_defaut = "Type de fichier non pris en charge."
