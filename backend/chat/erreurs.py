"""Erreurs propres au domaine `chat`.

Elles dérivent de `EchoHubError` pour hériter du contrat commun (`code`, `statut_http`,
`remediation`, `to_dict`) : la couche API traduit toutes les erreurs de la même façon, sans table
de correspondance dédiée au chat.

Seul ce qui n'a pas de sens hors du chat vit ici. Une génération demandée sans moteur d'inférence
disponible reste une `MoteurIndisponible` de `core` — c'est le même échec, quel que soit l'appelant.
"""

from __future__ import annotations

from backend.core import EchoHubError


class GenerationDejaEnCours(EchoHubError):
    """Une génération est déjà active sur cette conversation.

    Le domaine impose une génération à la fois par conversation : deux flux concurrents écriraient
    deux messages assistants pour un seul tour, et l'annulation ne saurait plus lequel viser.
    """

    code = "generation_deja_en_cours"
    statut_http = 409
    remediation_defaut = "Attendre la fin de la génération en cours, ou l'annuler avant d'en relancer une."


class MessageIntrouvable(EchoHubError):
    """Le message visé n'existe pas, ou n'appartient pas à la conversation indiquée.

    Les deux cas rendent la même erreur volontairement : répondre « il existe mais ailleurs »
    renseignerait sur le contenu d'une autre conversation sans qu'on l'ait demandé.
    """

    code = "message_introuvable"
    statut_http = 404
    remediation_defaut = "Recharger la conversation : le message a pu être supprimé entre-temps."


class BrancheInvalide(EchoHubError):
    """L'opération de branche demandée n'a pas de sens sur ce message.

    Deux cas mesurables : éditer une réponse du modèle (elle deviendrait un faux enregistrement de
    ce qu'il a produit), et rejouer un message sans aucun historique en amont — il ne resterait
    rien à envoyer au moteur.
    """

    code = "branche_invalide"
    statut_http = 422
    remediation_defaut = "Seul un message utilisateur s'édite ; une réponse se rejoue depuis son propre parent."


class ContratInferenceInvalide(EchoHubError):
    """Le moteur branché ne respecte pas le contrat attendu par `chat`.

    Distinguée de `MoteurIndisponible` : ici le moteur répond, mais ce qu'il rend n'est pas
    consommable. C'est un défaut de câblage entre domaines, pas une panne matérielle.
    """

    code = "contrat_inference_invalide"
    statut_http = 500
    remediation_defaut = (
        "Le domaine inference doit exposer une génération rendant un itérateur asynchrone "
        "de fragments (voir backend/chat/port_inference.py)."
    )
