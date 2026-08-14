"""Le processus fils qui transfère, et ce qu'il laisse derrière lui.

`huggingface_hub` n'expose aucun jeton d'annulation, et un thread Python ne s'interrompt pas. Le
transfert tourne donc dans un **processus séparé** : l'arrêter est immédiat, à n'importe quel
moment, et les fragments déjà écrits restent réutilisables pour une reprise.

Ce module est volontairement isolé du gestionnaire : son contenu doit rester importable dans un
processus démarré en `spawn`, c'est-à-dire sans rien présupposer de l'état du parent.
"""

from __future__ import annotations

import shutil
from multiprocessing.queues import Queue as FileProcessus
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download
from loguru import logger

from backend.models.storage import DOSSIER_FRAGMENTS


def executer_telechargement(
    depot: str,
    fichier: str | None,
    revision: str,
    dossier: str,
    jeton: str | None,
    motifs_ignores: list[str],
    retour: FileProcessus[dict[str, str]],
) -> None:
    """Corps du processus fils : le transfert, et rien d'autre.

    Le verdict repart par la file. L'état persistant reste la responsabilité du parent, seul à
    pouvoir le tenir cohérent si le fils est tué en cours de route.
    """
    try:
        if fichier:
            hf_hub_download(repo_id=depot, filename=fichier, revision=revision, local_dir=dossier, token=jeton)
        else:
            snapshot_download(
                repo_id=depot,
                revision=revision,
                local_dir=dossier,
                token=jeton,
                ignore_patterns=list(motifs_ignores),
            )
        retour.put({"resultat": "ok"})
    except Exception as exc:  # noqa: BLE001 — frontière externe : tout échec doit revenir au parent
        retour.put({"resultat": "erreur", "type": type(exc).__name__, "message": str(exc)})


def remediation(message: str) -> str:
    """Traduit le message d'erreur du Hub en action concrète, quand il est reconnaissable.

    La v1 remontait le message brut de la bibliothèque jusqu'à l'interface ; « 401 Client Error »
    ne dit pas qu'il faut accepter une licence puis renseigner un jeton.
    """
    minuscule = message.lower()
    if "401" in message or "403" in message or "gated" in minuscule:
        return (
            "Dépôt à accès restreint : accepter la licence sur Hugging Face, puis renseigner un "
            "HF_TOKEN qui y donne accès."
        )
    if "404" in message or "not found" in minuscule:
        return "Le dépôt ou le fichier n'existe pas (ou plus) sous ce nom : vérifier l'identifiant."
    if "space" in minuscule and "disk" in minuscule:
        return "Espace disque insuffisant sur le volume des modèles."
    return "Vérifier la connexion réseau, puis relancer : la reprise repart des octets déjà écrits."


def supprimer(dossier: Path, fichier: str | None) -> None:
    """Supprime ce qu'un téléchargement annulé a laissé.

    À n'appeler qu'après la mort confirmée du processus fils. L'inverse — supprimer pendant que la
    bibliothèque écrit — est exactement ce que faisait la v1, et le transfert échouait ensuite sur
    un `FileNotFoundError` sans rapport apparent avec l'annulation.
    """
    cible = dossier / fichier if fichier else dossier
    try:
        if fichier:
            cible.unlink(missing_ok=True)
            shutil.rmtree(dossier / DOSSIER_FRAGMENTS, ignore_errors=True)
        else:
            shutil.rmtree(dossier, ignore_errors=True)
    except OSError as exc:
        logger.error("Suppression de {} impossible : {}", cible, exc)
