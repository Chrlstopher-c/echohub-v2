"""Lecture de l'index des tenseurs d'un modèle safetensors, sans charger les poids.

Un fichier safetensors commence par `[taille_json:u64][json]` : l'en-tête décrit chaque tenseur
(type, forme, plage d'octets). Le lire coûte une lecture de quelques kilooctets et donne la liste
**réelle** des poids présents.

C'est indispensable parce qu'un `config.json` peut mentir : le cas mesuré sur la v1 est un AWQ qui
déclarait une tour de vision dont aucun poids n'existait dans les safetensors. Le chargement
échouait ensuite avec un message pointant un fichier, ce qui envoyait chercher au mauvais endroit.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field

from backend.core.errors import MetadonneesIllisibles

NOM_INDEX = "model.safetensors.index.json"
NOM_CONFIG = "config.json"

# Majorant de l'en-tête JSON : les plus gros modèles restent sous quelques mégaoctets. Au-delà, la
# longueur annoncée est corrompue et il ne faut surtout pas allouer.
LIMITE_OCTETS_ENTETE = 64 << 20

# Clé réservée du format : métadonnées libres, pas un tenseur.
CLE_METADONNEES = "__metadata__"


class InfoTenseurSafetensors(BaseModel):
    """Descripteur d'un tenseur tel qu'écrit dans l'en-tête d'un fichier safetensors."""

    nom: str
    dtype: str
    forme: tuple[int, ...]
    octets: int = Field(ge=0)
    fichier: str


class IndexSafetensors(BaseModel):
    """Vue consolidée des poids d'un modèle : ce qui est annoncé, et ce qui est réellement là."""

    dossier: str
    fichiers_lus: list[str]
    tenseurs: dict[str, InfoTenseurSafetensors]
    # Fichiers référencés par `model.safetensors.index.json` mais absents du disque.
    fichiers_manquants: list[str] = Field(default_factory=list)
    # Tenseurs promis par l'index mais absents des en-têtes réellement lus.
    tenseurs_manquants: list[str] = Field(default_factory=list)

    @property
    def octets_totaux(self) -> int:
        return sum(tenseur.octets for tenseur in self.tenseurs.values())


def lire_entete_fichier(chemin: Path) -> dict[str, InfoTenseurSafetensors]:
    """Tenseurs décrits par l'en-tête d'un unique fichier safetensors."""
    try:
        with chemin.open("rb") as fichier:
            brut_longueur = fichier.read(8)
            if len(brut_longueur) != 8:
                raise MetadonneesIllisibles(
                    f"Fichier safetensors tronqué : {chemin.name}",
                    details={"chemin": str(chemin)},
                )
            longueur = int(struct.unpack("<Q", brut_longueur)[0])
            if longueur <= 0 or longueur > LIMITE_OCTETS_ENTETE:
                raise MetadonneesIllisibles(
                    f"En-tête safetensors invalide ({longueur} octets annoncés) : {chemin.name}",
                    details={"chemin": str(chemin), "longueur_annoncee": longueur},
                )
            brut_json = fichier.read(longueur)
    except OSError as exc:
        logger.error("Lecture de l'en-tête safetensors {} impossible : {}", chemin, exc)
        raise MetadonneesIllisibles(
            f"Fichier safetensors illisible : {chemin.name}",
            details={"chemin": str(chemin), "cause": str(exc)},
        ) from exc

    return _decoder_entete(brut_json, chemin)


def _decoder_entete(brut_json: bytes, chemin: Path) -> dict[str, InfoTenseurSafetensors]:
    """Transforme l'en-tête JSON en descripteurs typés."""
    try:
        donnees = json.loads(brut_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("En-tête safetensors non décodable {} : {}", chemin, exc)
        raise MetadonneesIllisibles(
            f"En-tête safetensors non décodable : {chemin.name}",
            details={"chemin": str(chemin), "cause": str(exc)},
        ) from exc

    if not isinstance(donnees, dict):
        raise MetadonneesIllisibles(
            f"En-tête safetensors inattendu (objet JSON attendu) : {chemin.name}",
            details={"chemin": str(chemin)},
        )

    tenseurs: dict[str, InfoTenseurSafetensors] = {}
    for nom, description in donnees.items():
        if nom == CLE_METADONNEES or not isinstance(description, dict):
            continue
        tenseur = _construire_tenseur(nom, description, chemin)
        if tenseur is not None:
            tenseurs[nom] = tenseur
    return tenseurs


def _construire_tenseur(nom: str, description: dict[str, object], chemin: Path) -> InfoTenseurSafetensors | None:
    """Descripteur d'un tenseur, ou `None` si l'entrée est inexploitable."""
    forme = description.get("shape")
    bornes = description.get("data_offsets")
    dtype = description.get("dtype")
    if not isinstance(forme, list) or not isinstance(bornes, list) or len(bornes) != 2:
        logger.warning("Entrée de tenseur ignorée dans {} : {}", chemin.name, nom)
        return None
    debut, fin = bornes
    if not isinstance(debut, int) or not isinstance(fin, int) or fin < debut:
        logger.warning("Plage d'octets invalide pour {} dans {}", nom, chemin.name)
        return None
    return InfoTenseurSafetensors(
        nom=nom,
        dtype=str(dtype) if isinstance(dtype, str) else "inconnu",
        forme=tuple(int(dimension) for dimension in forme if isinstance(dimension, int)),
        octets=fin - debut,
        fichier=chemin.name,
    )


def _fichiers_annonces(dossier: Path) -> tuple[list[str], list[str]]:
    """Fichiers de poids et noms de tenseurs annoncés par l'index de sharding, s'il existe."""
    index = dossier / NOM_INDEX
    if not index.is_file():
        return [], []
    try:
        contenu = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("Index safetensors illisible {} : {}", index, exc)
        return [], []

    carte = contenu.get("weight_map") if isinstance(contenu, dict) else None
    if not isinstance(carte, dict):
        return [], []
    noms_tenseurs = [nom for nom in carte if isinstance(nom, str)]
    fichiers = sorted({valeur for valeur in carte.values() if isinstance(valeur, str)})
    return fichiers, noms_tenseurs


def lire_index(dossier: Path) -> IndexSafetensors:
    """Consolide les en-têtes de tous les safetensors d'un dossier et confronte l'index annoncé."""
    presents = sorted(dossier.glob("*.safetensors"))
    tenseurs: dict[str, InfoTenseurSafetensors] = {}
    lus: list[str] = []
    for chemin in presents:
        tenseurs.update(lire_entete_fichier(chemin))
        lus.append(chemin.name)

    annonces, noms_annonces = _fichiers_annonces(dossier)
    noms_presents = {chemin.name for chemin in presents}
    return IndexSafetensors(
        dossier=str(dossier),
        fichiers_lus=lus,
        tenseurs=tenseurs,
        fichiers_manquants=[nom for nom in annonces if nom not in noms_presents],
        tenseurs_manquants=[nom for nom in noms_annonces if nom not in tenseurs],
    )


def lire_config(dossier: Path) -> dict[str, object] | None:
    """Contenu de `config.json`, ou `None` s'il est absent ou illisible.

    Ce que ce fichier déclare n'est jamais tenu pour vrai : `coherence` le confronte à l'index des
    tenseurs, qui est la seule source vérifiable.
    """
    chemin = dossier / NOM_CONFIG
    if not chemin.is_file():
        return None
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("config.json illisible {} : {}", chemin, exc)
        return None
    return contenu if isinstance(contenu, dict) else None
