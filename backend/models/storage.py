"""Où vivent les modèles sur le disque, et ce qu'ils y pèsent réellement.

Seul endroit du domaine qui connaît la convention de nommage des dossiers. La v1 la dupliquait
dans cinq modules avec un chemin absolu codé en dur (`/mnt/models/echohub`) tombant hors du volume
Docker ; ici tout part de `Settings.models_dir`, qui est le répertoire monté en volume persistant.

La taille est toujours **mesurée** par parcours du disque, jamais reprise d'une annonce du Hub :
c'est la seule valeur qui reste vraie après un téléchargement partiel.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from loguru import logger

from backend.core.config import get_settings

# Séparateur des dossiers de modèles : `Qwen/Qwen3-8B-GGUF` -> `Qwen--Qwen3-8B-GGUF`. Le slash est
# interdit dans un nom de dossier, et le double tiret reste lisible dans un explorateur de fichiers.
SEPARATEUR_DEPOT = "--"

# Borne du parcours disque : au-delà, le dossier n'est pas un modèle mais une arborescence tierce.
LIMITE_FICHIERS_PARCOURUS = 200_000

# Sous-dossier où huggingface_hub range les fragments d'un téléchargement en cours. Il compte dans
# la taille réelle : c'est ce qui rend la progression honnête pendant un transfert.
DOSSIER_FRAGMENTS = ".cache"

# Dossier réservé aux états internes du domaine (journal des téléchargements). Préfixé d'un point,
# comme tout ce qui n'est pas un modèle, ce qui suffit à l'écarter des listages.
DOSSIER_INTERNE = ".echohub"


class FormatModele(str, Enum):
    """Format de poids. Les valeurs correspondent à la contrainte CHECK de la table `modeles`."""

    GGUF = "gguf"
    SAFETENSORS = "safetensors"


def racine_modeles() -> Path:
    """Répertoire racine où tous les modèles sont rangés."""
    return get_settings().models_dir


def nom_dossier(depot: str) -> str:
    """Nom de dossier correspondant à un dépôt Hugging Face."""
    return depot.replace("/", SEPARATEUR_DEPOT)


def depot_depuis_dossier(nom: str) -> str:
    """Dépôt correspondant à un nom de dossier.

    Conversion volontairement limitée au premier séparateur : un dépôt dont le nom contient
    lui-même `--` ne serait pas reconstitué exactement. Le registre stocke donc le dépôt en clair
    et cette fonction ne sert qu'au repérage des dossiers orphelins, où l'approximation est sans
    conséquence.
    """
    return nom.replace(SEPARATEUR_DEPOT, "/", 1)


def dossier_modele(depot: str) -> Path:
    """Dossier local d'un dépôt, qu'il existe ou non."""
    return racine_modeles() / nom_dossier(depot)


def identifiant(depot: str, fichier: str | None = None) -> str:
    """Identifiant stable d'une entrée du registre.

    Un même dépôt GGUF héberge plusieurs quantifications ; le fichier fait donc partie de l'identité
    quand il est précisé, sinon l'identité est celle du dépôt entier (cas safetensors).
    """
    return f"{depot}::{fichier}" if fichier else depot


def taille_reelle_octets(chemin: Path) -> int:
    """Somme des tailles de fichiers sous `chemin`, fragments de téléchargement compris.

    Un fichier disparu en cours de parcours (téléchargement concurrent) est ignoré plutôt que de
    faire échouer la mesure : une taille légèrement sous-estimée vaut mieux qu'une progression qui
    s'arrête sur une exception.
    """
    if not chemin.exists():
        return 0

    total = 0
    parcourus = 0
    try:
        for fichier in chemin.rglob("*"):
            parcourus += 1
            if parcourus > LIMITE_FICHIERS_PARCOURUS:
                logger.warning("Parcours de {} interrompu à {} fichiers", chemin, LIMITE_FICHIERS_PARCOURUS)
                break
            try:
                if fichier.is_file():
                    total += fichier.stat().st_size
            except OSError:
                continue
    except OSError as exc:
        logger.error("Mesure de la taille de {} interrompue : {}", chemin, exc)
    return total


def octets_fichier(chemin: Path) -> int:
    """Taille d'un fichier, ou 0 s'il n'existe pas encore."""
    try:
        return chemin.stat().st_size if chemin.is_file() else 0
    except OSError as exc:
        logger.warning("Taille de {} illisible : {}", chemin, exc)
        return 0


def octets_fragments(dossier: Path) -> int:
    """Octets déjà écrits par un téléchargement en cours, hors fichier final.

    `huggingface_hub` écrit ses fragments sous `.cache/huggingface/download`. Les compter est ce
    qui rend la progression réelle pendant un transfert, et ce qui permet d'annoncer honnêtement
    ce qu'une reprise n'aura pas à retélécharger.
    """
    cache = dossier / DOSSIER_FRAGMENTS
    if not cache.is_dir():
        return 0
    total = 0
    try:
        for fragment in cache.rglob("*.incomplete"):
            total += octets_fichier(fragment)
    except OSError as exc:
        logger.warning("Mesure des fragments de {} interrompue : {}", dossier, exc)
    return total


def fichiers_gguf(dossier: Path) -> list[Path]:
    """Fichiers GGUF présents dans un dossier de modèle, triés par nom.

    Les projecteurs multimodaux (`mmproj*`) sont exclus : ce sont des GGUF valides mais ce ne sont
    pas le modèle, et les confondre fausserait toute lecture de métadonnées.
    """
    try:
        trouves = sorted(dossier.rglob("*.gguf"))
    except OSError as exc:
        logger.error("Listage des GGUF de {} impossible : {}", dossier, exc)
        return []
    return [chemin for chemin in trouves if not chemin.name.lower().startswith("mmproj")]


def fichiers_safetensors(dossier: Path) -> list[Path]:
    """Fichiers safetensors présents dans un dossier de modèle, triés par nom."""
    try:
        return sorted(dossier.rglob("*.safetensors"))
    except OSError as exc:
        logger.error("Listage des safetensors de {} impossible : {}", dossier, exc)
        return []


def detecter_format(dossier: Path) -> FormatModele | None:
    """Format d'un modèle téléchargé, d'après les fichiers réellement présents.

    Le format vient du contenu du dossier, jamais du nom du dépôt : un dépôt appelé `...-GGUF` peut
    parfaitement n'avoir été téléchargé qu'en partie.
    """
    if fichiers_gguf(dossier):
        return FormatModele.GGUF
    if fichiers_safetensors(dossier):
        return FormatModele.SAFETENSORS
    return None


def est_present(depot: str, fichier: str | None = None) -> bool:
    """Vrai si le modèle est effectivement sur le disque, pas seulement inscrit au registre."""
    dossier = dossier_modele(depot)
    if fichier:
        return (dossier / fichier).exists()
    return dossier.is_dir() and any(dossier.iterdir())


def dossier_interne() -> Path:
    """Dossier des états internes du domaine, créé à la demande."""
    chemin = racine_modeles() / DOSSIER_INTERNE
    try:
        chemin.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Création du dossier interne {} impossible : {}", chemin, exc)
    return chemin


def dossiers_presents() -> list[Path]:
    """Dossiers de modèles présents sous la racine ; tout dossier caché est écarté."""
    racine = racine_modeles()
    if not racine.is_dir():
        return []
    try:
        return sorted(chemin for chemin in racine.iterdir() if chemin.is_dir() and not chemin.name.startswith("."))
    except OSError as exc:
        logger.error("Listage de la racine des modèles {} impossible : {}", racine, exc)
        return []
