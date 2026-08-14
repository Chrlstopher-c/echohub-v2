"""Hiérarchie d'exceptions du domaine EchoHub.

Chaque erreur porte trois choses : ce qui a échoué (`message`), ce que l'utilisateur peut y faire
(`remediation`), et de quoi diagnostiquer (`details`). La v1 remontait des `Exception` nues jusqu'à
l'interface, qui affichait des traces Python — inexploitables pour décider quoi corriger.

`code` et `statut_http` existent pour que la couche API traduise une erreur métier en réponse HTTP
sans réintroduire une table de correspondance ailleurs.
"""

from __future__ import annotations

from typing import Any


class EchoHubError(Exception):
    """Base de toutes les erreurs métier. Ne jamais lever directement — utiliser une sous-classe."""

    code: str = "erreur_interne"
    statut_http: int = 500
    remediation_defaut: str = ""

    def __init__(
        self,
        message: str,
        *,
        remediation: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.remediation = remediation or self.remediation_defaut
        self.details: dict[str, Any] = details or {}

    def __str__(self) -> str:
        if not self.remediation:
            return self.message
        # Séparateur ASCII volontaire : une console Windows en cp1252 lève UnicodeEncodeError
        # sur « → » et fait disparaître le message d'erreur qu'on cherchait justement à lire.
        return f"{self.message} -> {self.remediation}"

    def to_dict(self) -> dict[str, Any]:
        """Représentation sérialisable, consommée telle quelle par la couche API."""
        return {
            "code": self.code,
            "message": self.message,
            "remediation": self.remediation,
            "details": self.details,
        }


class ConfigurationInvalide(EchoHubError):
    """Réglage ou chemin inutilisable : la variable d'environnement ne mène nulle part d'écrivable."""

    code = "configuration_invalide"
    statut_http = 500
    remediation_defaut = "Corriger les variables d'environnement (MODELS_DIR, XDG_DATA_HOME) et relancer."


class ErreurPersistance(EchoHubError):
    """Échec d'une opération SQLite : ouverture, schéma, lecture ou écriture."""

    code = "erreur_persistance"
    statut_http = 500
    remediation_defaut = "Vérifier l'accès au fichier de base et l'espace disque du volume de données."


class ModeleIntrouvable(EchoHubError):
    """Le modèle demandé n'est ni dans le registre local ni sur le disque."""

    code = "modele_introuvable"
    statut_http = 404
    remediation_defaut = "Vérifier l'identifiant, ou retélécharger le modèle depuis l'écran Modèles."


class MetadonneesIllisibles(EchoHubError):
    """En-tête GGUF ou `config.json` illisible, tronqué, ou en contradiction avec les poids réels.

    Cas mesuré sur la v1 : un AWQ déclarait une tour de vision dont aucun poids n'existait. Une
    métadonnée douteuse doit remonter ici, jamais être remplacée par une estimation.
    """

    code = "metadonnees_illisibles"
    statut_http = 422
    remediation_defaut = "Le fichier est incomplet ou incohérent : relancer le téléchargement du modèle."


class TelechargementEchoue(EchoHubError):
    """Échec de récupération d'un dépôt ou d'un fichier depuis Hugging Face."""

    code = "telechargement_echoue"
    statut_http = 502
    remediation_defaut = "Vérifier la connexion réseau et, pour un dépôt privé, la validité de HF_TOKEN."


class MoteurIndisponible(EchoHubError):
    """Le moteur d'inférence demandé n'est pas installé, pas démarré, ou ne répond plus."""

    code = "moteur_indisponible"
    statut_http = 503
    remediation_defaut = "Installer ou redémarrer le moteur depuis l'écran Système avant de charger un modèle."


class InstallationMoteurEchouee(EchoHubError):
    """La compilation ou l'installation d'un moteur (llama.cpp, vLLM) a échoué."""

    code = "installation_moteur_echouee"
    statut_http = 500
    remediation_defaut = "Consulter le journal d'installation : chaîne CUDA, version de pilote ou venv en cause."


class RessourceInsuffisante(EchoHubError):
    """La mémoire (VRAM ou RAM) réellement libre ne couvre pas le besoin mesuré.

    Porte les deux quantités pour que le planificateur puisse dégrader avec un écart chiffré, au
    lieu de retenter au hasard.
    """

    code = "ressource_insuffisante"
    statut_http = 507
    remediation_defaut = "Décharger le modèle en cours ou réduire le contexte : le plan sera recalculé plus bas."

    def __init__(
        self,
        message: str,
        *,
        requis_octets: int | None = None,
        disponible_octets: int | None = None,
        remediation: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        complements: dict[str, Any] = dict(details or {})
        complements.update({"requis_octets": requis_octets, "disponible_octets": disponible_octets})
        super().__init__(message, remediation=remediation, details=complements)
        self.requis_octets = requis_octets
        self.disponible_octets = disponible_octets


class ChargementEchoue(EchoHubError):
    """Le moteur a refusé le plan de chargement. Déclenche une replanification plus conservatrice."""

    code = "chargement_echoue"
    statut_http = 500
    remediation_defaut = "Le plan va être dégradé automatiquement ; en cas d'échec répété, réduire le contexte."


class PlanificationImpossible(EchoHubError):
    """Même le mode minimal ne tient pas sur cette machine : aucun plan valide n'existe."""

    code = "planification_impossible"
    statut_http = 507
    remediation_defaut = "Ce modèle dépasse les capacités de la machine : choisir une quantification plus basse."


class ConversationIntrouvable(EchoHubError):
    """La conversation demandée n'existe pas ou a été supprimée."""

    code = "conversation_introuvable"
    statut_http = 404
    remediation_defaut = "Rafraîchir la liste des conversations."
