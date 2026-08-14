"""Configuration des logs — loguru en sortie console lisible + fichier.

Deux choix explicites :
- le fichier est remis à zéro à chaque démarrage (`mode="w"`), jamais accumulé : un journal qui
  couvre le seul run en cours est lisible, un journal de trois semaines ne l'est pas ;
- les logs de la bibliothèque standard (uvicorn, httpx, huggingface_hub) sont relayés vers loguru,
  sinon la moitié des messages du backend sortent dans un format différent et hors du fichier.
"""

from __future__ import annotations

import logging as journal_standard
import sys

from loguru import logger

from backend.core.config import Settings, get_settings

FORMAT_CONSOLE = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
FORMAT_FICHIER = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"

NOM_FICHIER_LOG = "backend.log"
TAILLE_ROTATION = "20 MB"

# Garde-fou de la remontée de pile du relais stdlib : une chaîne d'appels ne dépasse jamais cela.
_PROFONDEUR_MAX = 30

# Bibliothèques dont les loggers doivent passer par le relais plutôt que par leurs propres handlers.
_LOGGERS_A_RELAYER = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "httpx", "huggingface_hub")


class RelaisStdlib(journal_standard.Handler):
    """Handler stdlib qui réémet chaque enregistrement dans loguru, niveau et origine préservés."""

    def emit(self, record: journal_standard.LogRecord) -> None:
        try:
            niveau: str | int = logger.level(record.levelname).name
        except ValueError:
            niveau = record.levelno

        cadre = journal_standard.currentframe()
        profondeur = 0
        # Remonter jusqu'au vrai appelant pour que {name}:{line} ne pointe pas sur ce fichier.
        while cadre and profondeur < _PROFONDEUR_MAX and cadre.f_code.co_filename == journal_standard.__file__:
            cadre = cadre.f_back
            profondeur += 1

        logger.opt(depth=profondeur, exception=record.exc_info).log(niveau, record.getMessage())


def _brancher_stdlib(niveau: str) -> None:
    """Redirige la journalisation standard vers loguru et neutralise les handlers concurrents."""
    journal_standard.basicConfig(handlers=[RelaisStdlib()], level=niveau, force=True)
    for nom in _LOGGERS_A_RELAYER:
        journal = journal_standard.getLogger(nom)
        journal.handlers = [RelaisStdlib()]
        journal.propagate = False


def _ajouter_sortie_fichier(parametres: Settings) -> None:
    """Ajoute le sink fichier. Un disque indisponible dégrade vers la console, il n'arrête pas le backend."""
    try:
        parametres.preparer_repertoires()
        logger.add(
            parametres.logs_dir / NOM_FICHIER_LOG,
            level=parametres.log_level,
            format=FORMAT_FICHIER,
            rotation=TAILLE_ROTATION,
            retention=2,
            mode="w",
            encoding="utf-8",
            enqueue=True,
            backtrace=True,
            diagnose=False,
        )
    except (OSError, ValueError) as exc:
        logger.warning("Journal fichier indisponible, sortie console seule : {}", exc)


def setup_logging(parametres: Settings | None = None, *, capturer_stdlib: bool = True) -> None:
    """Configure loguru. Idempotent : les sinks existants sont retirés avant d'en reposer."""
    parametres = parametres or get_settings()

    logger.remove()
    logger.add(
        sys.stderr,
        level=parametres.log_level,
        format=FORMAT_CONSOLE,
        colorize=True,
        backtrace=True,
        # `diagnose` expose les valeurs des variables locales dans les traces : jamais hors debug,
        # un token ou un chemin utilisateur s'y retrouverait.
        diagnose=parametres.log_level in ("TRACE", "DEBUG"),
    )

    if parametres.log_to_file:
        _ajouter_sortie_fichier(parametres)

    if capturer_stdlib:
        _brancher_stdlib(parametres.log_level)

    logger.debug("Logs configurés (niveau {}, fichier {})", parametres.log_level, parametres.log_to_file)
