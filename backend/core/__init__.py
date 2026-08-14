"""Socle partagé du backend : configuration, logs, erreurs, persistance.

`core` n'est pas un domaine métier — il ne connaît ni les modèles, ni les moteurs, ni le
planificateur. Les domaines (`system`, `engines`, `models`, `inference`, `chat`) importent
uniquement ce qui est exposé ici, jamais un sous-module interne.

Usage typique au démarrage du backend :

    from backend.core import get_settings, setup_logging, init_db

    parametres = get_settings()
    setup_logging(parametres)
    init_db()
"""

from backend.core.config import NOM_APPLICATION, Settings, get_settings, reset_settings_cache
from backend.core.db import (
    SCHEMA_VERSION,
    Conversation,
    Message,
    ModeleEnregistre,
    close_connection,
    execute,
    executemany,
    fetch_all,
    fetch_one,
    get_connection,
    init_db,
    maintenant,
    transaction,
)
from backend.core.errors import (
    ChargementEchoue,
    ConfigurationInvalide,
    ConversationIntrouvable,
    EchoHubError,
    ErreurPersistance,
    InstallationMoteurEchouee,
    MetadonneesIllisibles,
    ModeleIntrouvable,
    MoteurIndisponible,
    PlanificationImpossible,
    RessourceInsuffisante,
    TelechargementEchoue,
)
from backend.core.logging import setup_logging

__all__ = [
    # Configuration
    "NOM_APPLICATION",
    "Settings",
    "get_settings",
    "reset_settings_cache",
    # Logs
    "setup_logging",
    # Erreurs
    "EchoHubError",
    "ConfigurationInvalide",
    "ErreurPersistance",
    "ModeleIntrouvable",
    "MetadonneesIllisibles",
    "TelechargementEchoue",
    "MoteurIndisponible",
    "InstallationMoteurEchouee",
    "RessourceInsuffisante",
    "ChargementEchoue",
    "PlanificationImpossible",
    "ConversationIntrouvable",
    # Persistance
    "SCHEMA_VERSION",
    "Conversation",
    "Message",
    "ModeleEnregistre",
    "init_db",
    "get_connection",
    "close_connection",
    "transaction",
    "execute",
    "executemany",
    "fetch_one",
    "fetch_all",
    "maintenant",
]
