"""Ce que le disque contient réellement — y compris ce que le registre refuse.

Le registre n'inscrit que ce qui est chargeable, et il a raison : un fichier auxiliaire ou un
téléchargement inachevé ne doit pas apparaître comme un modèle utilisable. Mais le refuser au
registre le rendait invisible ET indestructible depuis l'interface : douze gigaoctets sur le disque
que rien ne montrait et que rien ne permettait d'effacer.

Ce module regarde donc le disque tel qu'il est. Il ne juge pas de la même façon que le registre :
il rend TOUT, en distinguant ce qui est inscrit de ce qui ne l'est pas, et en disant pourquoi.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger
from pydantic import BaseModel

from backend.core.errors import ModeleIntrouvable
from backend.models.gguf_metadata import lire_metadonnees
from backend.models.registry import lister
from backend.models.storage import (
    depot_depuis_dossier,
    dossiers_presents,
    fichiers_gguf,
    fichiers_safetensors,
    racine_modeles,
    taille_reelle_octets,
)


class DossierDisque(BaseModel):
    """Un dossier de la racine des modèles, inscrit au registre ou non."""

    dossier: str
    depot: str
    taille_octets: int
    nb_fichiers_poids: int
    inscrit: bool
    # Vide quand `inscrit` : il n'y a rien à expliquer d'un modèle qui fonctionne.
    raison: str = ""
    remediation: str = ""


def _diagnostiquer(chemin: Path) -> tuple[str, str]:
    """Pourquoi ce dossier n'est pas inscriptible, dit avec les mots du domaine.

    On relit le fichier plutôt que de mémoriser le message d'une synchronisation antérieure : la
    cause doit refléter le disque maintenant, pas ce qu'il était au dernier passage.
    """
    poids = fichiers_gguf(chemin) or fichiers_safetensors(chemin)
    if not poids:
        return (
            "Aucun fichier de poids dans ce dossier.",
            "Téléchargement jamais abouti : le relancer, ou supprimer le dossier.",
        )
    try:
        lire_metadonnees(poids[0])
    except Exception as exc:  # noqa: BLE001 — toute cause de lecture doit devenir un texte affichable
        return (str(exc), "Fichier auxiliaire ou incomplet : vérifier la variante choisie sur le Hub.")
    return ("Présent sur le disque mais absent du registre.", "Lancer une synchronisation.")


def inventaire() -> list[DossierDisque]:
    """Tous les dossiers de la racine, avec leur taille réelle et leur statut."""
    inscrits = {entree.depot for entree in lister()}
    resultat: list[DossierDisque] = []
    for chemin in dossiers_presents():
        depot = depot_depuis_dossier(chemin.name)
        poids = fichiers_gguf(chemin) + fichiers_safetensors(chemin)
        inscrit = depot in inscrits
        raison, remediation = ("", "") if inscrit else _diagnostiquer(chemin)
        resultat.append(
            DossierDisque(
                dossier=chemin.name,
                depot=depot,
                taille_octets=taille_reelle_octets(chemin),
                nb_fichiers_poids=len(poids),
                inscrit=inscrit,
                raison=raison,
                remediation=remediation,
            )
        )
    return resultat


def supprimer_dossier(nom: str) -> int:
    """Efface un dossier de modèles et rend les octets libérés.

    Le nom est résolu SOUS la racine et vérifié : un nom contenant `..` ou un chemin absolu
    sortirait de l'arborescence des modèles, et cette fonction supprime récursivement. Le contrôle
    n'est pas théorique — le nom vient d'une URL.
    """
    racine = racine_modeles().resolve()
    cible = (racine / nom).resolve()
    if cible == racine or racine not in cible.parents:
        raise ModeleIntrouvable(
            f"« {nom} » ne désigne pas un dossier de modèles.",
            details={"dossier": nom},
        )
    if not cible.is_dir():
        raise ModeleIntrouvable(f"Aucun dossier « {nom} » sur le disque.", details={"dossier": nom})

    liberes = taille_reelle_octets(cible)
    try:
        shutil.rmtree(cible)
    except OSError as exc:
        logger.error("Suppression du dossier {} impossible : {}", cible, exc)
        raise ModeleIntrouvable(
            f"Le dossier « {nom} » n'a pas pu être supprimé : {exc}",
            remediation="Vérifier qu'aucun modèle de ce dossier n'est chargé, puis réessayer.",
            details={"dossier": nom},
        ) from exc
    logger.info("Dossier {} supprimé ({:.2f} Gio libérés)", nom, liberes / 2**30)
    return liberes
