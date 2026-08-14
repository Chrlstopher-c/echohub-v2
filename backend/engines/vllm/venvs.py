"""Inventaire des venvs vLLM : chemins, marqueur d'installation, lecture de l'état sur disque.

Plusieurs versions de vLLM cohabitent, chacune dans son propre venv sous `<engines_dir>/vllm/`.
La question à laquelle ce module répond est la seule qui compte pour le reste de l'application :
**ce venv est-il utilisable, oui ou non ?**

La réponse ne peut pas être « le dossier existe ». La v1 répondait en substance cela — un venv
créé, vLLM jamais installé dedans, et un `ModuleNotFoundError` sans explication au premier
chargement de modèle. La réponse retenue ici est un **marqueur écrit en deux temps** :

1. au début de l'installation, un marqueur `en_cours` ;
2. à la toute fin, et seulement après que la sonde a confirmé l'import, un marqueur `valide`.

Un process tué entre les deux — conteneur redémarré, requête annulée, machine coupée — laisse
donc un marqueur `en_cours`, et le venv est signalé INCOMPLET. Aucun état intermédiaire ne peut
se faire passer pour valide, y compris après un `SIGKILL` qui n'exécute aucun code de nettoyage.

Choix assumé : l'installation se fait directement au chemin final plutôt que dans un dossier de
travail renommé à la fin. Un venv embarque son propre chemin absolu dans les scripts de `bin/`,
qu'un renommage casserait silencieusement. L'atomicité vient donc du marqueur, pas du système de
fichiers — et le marqueur, lui, est bien écrit de façon atomique (fichier temporaire + `replace`).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from backend.core import InstallationMoteurEchouee, get_settings
from backend.engines.modeles import MarqueurInstallation, StatutMoteur, VersionVllm

SOUS_DOSSIER = "vllm"
NOM_MARQUEUR = "echohub-installation.json"

# Sonde exécutée par l'interpréteur d'un venv vLLM. Déclarée ici parce que « où trouver quoi dans
# un venv » est le sujet de ce module, et que l'installation comme la vérification s'en servent.
SCRIPT_SONDE = Path(__file__).with_name("sonde.py")

# Un `import vllm` à froid coûte des dizaines de secondes (torch, extensions CUDA). Au-delà de
# cette échéance, l'installation est considérée comme non validable plutôt que d'attendre sans fin.
TIMEOUT_SONDE_S = 300.0

# Le nom de version devient un nom de dossier : le motif interdit toute remontée de chemin et tout
# caractère qui ferait échouer une commande shell côté outils tiers.
_MOTIF_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$")

# Borne de parcours du répertoire : un inventaire ne doit pas dépendre de ce qu'un tiers a déposé
# là. Au-delà, on tronque en le signalant plutôt que de balayer sans limite.
MAX_VERSIONS_LISTEES = 64


def valider_version(version: str) -> str:
    """Valide un identifiant de version destiné à devenir un nom de dossier."""
    nettoye = version.strip()
    if ".." in nettoye or not _MOTIF_VERSION.match(nettoye):
        raise InstallationMoteurEchouee(
            f"Identifiant de version vLLM invalide : {version!r}",
            remediation="Utiliser une version publiée sur PyPI, par exemple 0.21.0.",
            details={"version": version},
        )
    return nettoye


def racine() -> Path:
    """Répertoire parent de tous les venvs vLLM, sous le volume persistant des moteurs."""
    return get_settings().engines_dir / SOUS_DOSSIER


def chemin_version(version: str) -> Path:
    return racine() / valider_version(version)


def python_de(dossier: Path) -> Path:
    """Interpréteur du venv. Windows range ses exécutables ailleurs que les systèmes POSIX."""
    if os.name == "nt":
        return dossier / "Scripts" / "python.exe"
    return dossier / "bin" / "python"


def cle_tri_version(version: str) -> tuple[int, ...]:
    """Clé de tri numérique : un tri lexical placerait 0.9.0 après 0.21.0."""
    morceaux = re.findall(r"\d+", version)[:4]
    return tuple(int(morceau) for morceau in morceaux) if morceaux else (0,)


def lire_marqueur(dossier: Path) -> MarqueurInstallation | None:
    """Marqueur du venv, ou `None` s'il est absent, illisible ou incohérent."""
    fichier = dossier / NOM_MARQUEUR
    try:
        contenu = fichier.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("Marqueur illisible dans {} : {}", dossier, exc)
        return None
    try:
        return MarqueurInstallation.model_validate_json(contenu)
    except ValidationError as exc:
        logger.warning("Marqueur incohérent dans {} : {}", dossier, exc)
        return None


def ecrire_marqueur(dossier: Path, marqueur: MarqueurInstallation) -> None:
    """Écrit le marqueur de façon atomique — un marqueur tronqué vaudrait un venv menteur."""
    fichier = dossier / NOM_MARQUEUR
    temporaire = fichier.with_suffix(".json.tmp")
    try:
        temporaire.write_text(marqueur.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporaire, fichier)
    except OSError as exc:
        logger.error("Écriture du marqueur impossible dans {} : {}", dossier, exc)
        raise InstallationMoteurEchouee(
            f"Impossible d'écrire l'état d'installation dans {dossier}.",
            remediation="Vérifier les droits et l'espace disque du volume des moteurs.",
            details={"cause": str(exc)},
        ) from exc


def taille_octets(dossier: Path) -> int | None:
    """Taille sur disque, mesurée une seule fois à l'installation puis conservée dans le marqueur."""
    try:
        return sum(fichier.stat().st_size for fichier in dossier.rglob("*") if fichier.is_file())
    except OSError as exc:
        logger.warning("Taille de {} non mesurable : {}", dossier, exc)
        return None


def _etat_depuis_marqueur(dossier: Path, version: str) -> VersionVllm:
    """État rapide, lu sur le disque seul — sans lancer la sonde, qui coûte une minute à froid."""
    python = python_de(dossier)
    marqueur = lire_marqueur(dossier)
    if marqueur is None or marqueur.statut != "valide":
        motif = "aucun marqueur d'installation" if marqueur is None else "installation interrompue"
        return VersionVllm(
            version=version,
            chemin=dossier,
            python=python,
            statut=StatutMoteur.INCOMPLET,
            diagnostic=f"Venv inutilisable ({motif}) : il ne sera jamais proposé au chargement.",
        )
    if not python.exists():
        return VersionVllm(
            version=version,
            chemin=dossier,
            python=python,
            statut=StatutMoteur.DEFAILLANT,
            diagnostic="Le marqueur est valide mais l'interpréteur du venv a disparu.",
        )
    return VersionVllm(
        version=version,
        chemin=dossier,
        python=python,
        statut=StatutMoteur.FONCTIONNEL,
        version_installee=marqueur.version_vllm,
        version_transformers=marqueur.version_transformers,
        version_torch=marqueur.version_torch,
        architectures_gpu=marqueur.architectures_gpu,
        taille_octets=marqueur.taille_octets,
        installee_le=marqueur.validee_le,
        diagnostic="Installation validée par sonde à la fin de son installation.",
    )


def inventaire() -> list[VersionVllm]:
    """Toutes les versions présentes, triées de la plus récente à la plus ancienne."""
    dossier_racine = racine()
    if not dossier_racine.is_dir():
        return []
    try:
        entrees = sorted(entree for entree in dossier_racine.iterdir() if entree.is_dir())
    except OSError as exc:
        logger.error("Inventaire des venvs vLLM impossible dans {} : {}", dossier_racine, exc)
        return []

    if len(entrees) > MAX_VERSIONS_LISTEES:
        logger.warning("{} dossiers sous {}, inventaire tronqué", len(entrees), dossier_racine)
        entrees = entrees[:MAX_VERSIONS_LISTEES]

    versions = [_etat_depuis_marqueur(entree, entree.name) for entree in entrees]
    return sorted(versions, key=lambda etat: cle_tri_version(etat.version), reverse=True)


def supprimer(version: str) -> None:
    """Supprime définitivement un venv. Refuse silencieusement de sortir de son répertoire."""
    dossier = chemin_version(version)
    if not dossier.is_dir():
        raise InstallationMoteurEchouee(
            f"Version vLLM {version} absente : rien à supprimer.",
            remediation="Rafraîchir la liste des versions installées.",
        )
    try:
        shutil.rmtree(dossier)
    except OSError as exc:
        logger.error("Suppression de {} échouée : {}", dossier, exc)
        raise InstallationMoteurEchouee(
            f"Suppression du venv vLLM {version} impossible.",
            remediation="Vérifier qu'aucun process vLLM de cette version ne tourne encore.",
            details={"cause": str(exc)},
        ) from exc
    logger.info("Venv vLLM supprimé : {}", dossier)


def nettoyer_residu(dossier: Path) -> None:
    """Efface un venv non valide avant réinstallation. Une réinstallation part toujours du vide."""
    if not dossier.exists():
        return
    try:
        shutil.rmtree(dossier)
        logger.warning("Résidu d'installation supprimé avant réinstallation : {}", dossier)
    except OSError as exc:
        logger.error("Nettoyage de {} impossible : {}", dossier, exc)
        raise InstallationMoteurEchouee(
            f"Impossible de repartir d'un état propre pour {dossier.name}.",
            remediation="Supprimer le dossier à la main, puis relancer l'installation.",
            details={"cause": str(exc)},
        ) from exc
