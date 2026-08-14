"""Recherche de modèles sur Hugging Face — métadonnées exploitables, pas du brut.

Ce module rend ce que le Hub annonce, en le nommant pour ce que c'est : une **déclaration**. Rien
de ce qui en sort n'a valeur de mesure. La v1 confondait les deux et calculait, à partir du nom
d'un dépôt, un nombre de paramètres, une fenêtre de contexte et une estimation de VRAM ; les trois
étaient faux sur le premier modèle sérieux rencontré.

Ici, la seule vérité mesurée arrive après téléchargement, par `gguf_metadata`. Avant, on affiche
des tailles de fichiers et des étiquettes — l'étiquette de quantification portée par un nom de
fichier sert à choisir quoi télécharger, jamais à calculer quoi que ce soit.
"""

from __future__ import annotations

import re
from enum import Enum
from itertools import islice
from typing import Iterable, Iterator, Literal

from huggingface_hub import HfApi
from huggingface_hub import ModelInfo as InfoDepotHF
from loguru import logger
from pydantic import BaseModel, Field

from backend.core.config import get_settings
from backend.core.errors import TelechargementEchoue
from backend.models.storage import FormatModele, est_present

# Marge de surlecture : la déduplication entre passes de filtre retire des entrées, il faut donc
# demander un peu plus que la page pour ne pas la rendre incomplète.
MARGE_PAGINATION = 20
LIMITE_RESULTATS_BRUTS = 1_000
TAILLE_PAGE_MAX = 100

MOTIF_VARIANTE = re.compile(
    r"(IQ\d+_[A-Z]+|Q\d+_K_[MSL]|Q\d+_K|Q\d+_\d|Q\d+|BF16|F16|F32|MXFP4)",
    re.IGNORECASE,
)


class FormatRecherche(str, Enum):
    """Formats de poids sur lesquels filtrer. Ce sont des étiquettes du Hub, pas des vérifications."""

    GGUF = "gguf"
    AWQ = "awq"
    GPTQ = "gptq"
    SAFETENSORS = "safetensors"


class TriRecherche(str, Enum):
    """Critères de tri acceptés par l'API du Hub."""

    TELECHARGEMENTS = "downloads"
    MENTIONS = "likes"
    CREATION = "created_at"
    MODIFICATION = "last_modified"
    TENDANCE = "trending_score"


Ordre = Literal["desc", "asc"]


class FichierDepot(BaseModel):
    """Un fichier du dépôt. `etiquette` vient du nom de fichier : c'est une intention, pas un fait."""

    nom: str
    taille_octets: int | None = None
    etiquette: str | None = None


class MetadonneesAnnoncees(BaseModel):
    """Ce que le Hub dit du modèle sans qu'on ait ouvert un seul octet de poids.

    Systématiquement présenté comme « annoncé » dans l'interface : ces valeurs servent à choisir un
    dépôt, jamais à dimensionner un chargement.
    """

    architecture: str | None = None
    contexte: int | None = None
    nb_parametres: int | None = None


class ResultatRecherche(BaseModel):
    """Un dépôt tel que le Hub le décrit, complété par ce que l'on sait localement."""

    depot: str
    nom: str
    auteur: str | None = None
    telechargements: int | None = None
    mentions: int | None = None
    tendance: int | None = None
    modifie_le: str | None = None
    gated: bool = False
    tache: str | None = None
    etiquettes: list[str] = Field(default_factory=list)
    formats: list[FormatModele] = Field(default_factory=list)
    fichiers_gguf: list[FichierDepot] = Field(default_factory=list)
    taille_totale_octets: int | None = None
    annonce: MetadonneesAnnoncees = Field(default_factory=MetadonneesAnnoncees)
    deja_telecharge: bool = False


class PageRecherche(BaseModel):
    """Une page de résultats, avec de quoi savoir s'il faut proposer la suivante."""

    resultats: list[ResultatRecherche]
    page: int = Field(ge=0)
    taille_page: int = Field(gt=0)
    fin_atteinte: bool


def _api() -> HfApi:
    """Client Hugging Face configuré avec le jeton, s'il y en a un."""
    jeton = get_settings().hf_token
    return HfApi(token=jeton.get_secret_value() if jeton else None)


def _echec(action: str, exc: Exception, **details: object) -> TelechargementEchoue:
    """Traduit un échec du Hub en erreur du domaine.

    L'exception d'origine est volontairement attrapée large en amont : selon la version,
    `huggingface_hub` remonte des erreurs httpx, requests ou système, et figer la liste ici ferait
    passer un vrai échec réseau pour un plantage interne.
    """
    logger.error("Hugging Face — {} : {}", action, exc)
    return TelechargementEchoue(f"Hugging Face : {action} a échoué.", details={"cause": str(exc), **details})


def etiquette_quantification(nom_fichier: str) -> str | None:
    """Étiquette de quantification portée par un nom de fichier GGUF, ou `None`.

    Sert à distinguer deux fichiers d'un même dépôt dans une liste. Interdit d'usage pour tout
    calcul : la quantification réelle se lit dans l'en-tête, une fois le fichier présent.
    """
    trouve = MOTIF_VARIANTE.search(nom_fichier.upper())
    return trouve.group(1).upper() if trouve else None


def _fichiers_gguf(info: InfoDepotHF) -> list[FichierDepot]:
    """Fichiers GGUF du dépôt, projecteurs multimodaux exclus."""
    fichiers: list[FichierDepot] = []
    for jumeau in info.siblings or []:
        nom = jumeau.rfilename
        if not nom.lower().endswith(".gguf") or nom.lower().startswith("mmproj"):
            continue
        fichiers.append(
            FichierDepot(nom=nom, taille_octets=getattr(jumeau, "size", None), etiquette=etiquette_quantification(nom))
        )
    return sorted(fichiers, key=lambda fichier: fichier.nom)


def _formats(info: InfoDepotHF) -> list[FormatModele]:
    """Formats de poids présents dans le dépôt, d'après la liste de ses fichiers."""
    noms = [jumeau.rfilename.lower() for jumeau in info.siblings or []]
    formats: list[FormatModele] = []
    if any(nom.endswith(".gguf") for nom in noms):
        formats.append(FormatModele.GGUF)
    if any(nom.endswith(".safetensors") for nom in noms):
        formats.append(FormatModele.SAFETENSORS)
    return formats


def _taille_totale(info: InfoDepotHF) -> int | None:
    """Somme des tailles annoncées, ou `None` si le Hub ne les a pas fournies."""
    tailles = [getattr(jumeau, "size", None) for jumeau in info.siblings or []]
    connues = [taille for taille in tailles if isinstance(taille, int)]
    return sum(connues) if connues else None


def _annonce(info: InfoDepotHF) -> MetadonneesAnnoncees:
    """Métadonnées GGUF telles que le Hub les publie, sans les recalculer."""
    brut = getattr(info, "gguf", None) or {}
    parametres = getattr(getattr(info, "safetensors", None), "total", None)
    contexte = brut.get("context_length") if isinstance(brut, dict) else None
    architecture = brut.get("architecture") if isinstance(brut, dict) else None
    return MetadonneesAnnoncees(
        architecture=architecture if isinstance(architecture, str) else None,
        contexte=contexte if isinstance(contexte, int) else None,
        nb_parametres=parametres if isinstance(parametres, int) else None,
    )


def _convertir(info: InfoDepotHF) -> ResultatRecherche:
    """Projette un dépôt du Hub sur le modèle du domaine."""
    depot = info.id
    auteur = info.author or (depot.split("/")[0] if "/" in depot else None)
    modifie = info.last_modified
    return ResultatRecherche(
        depot=depot,
        nom=depot.split("/")[-1],
        auteur=auteur,
        telechargements=info.downloads,
        mentions=info.likes,
        tendance=getattr(info, "trending_score", None),
        modifie_le=modifie.date().isoformat() if modifie else None,
        gated=bool(info.gated),
        tache=info.pipeline_tag,
        etiquettes=list(info.tags or []),
        formats=_formats(info),
        fichiers_gguf=_fichiers_gguf(info),
        taille_totale_octets=_taille_totale(info),
        annonce=_annonce(info),
        deja_telecharge=est_present(depot),
    )


def _lister(requete: str, etiquette: str | None, tri: TriRecherche, limite: int) -> Iterator[InfoDepotHF]:
    """Une passe de listage sur le Hub, bornée en nombre de résultats."""
    try:
        flux = _api().list_models(
            search=requete or None,
            filter=etiquette,
            sort=tri.value,
            limit=limite,
            full=True,
        )
        return iter(list(islice(flux, limite)))
    except Exception as exc:  # noqa: BLE001 — frontière externe, cf. `_echec`
        raise _echec("la recherche", exc, requete=requete, etiquette=etiquette) from exc


def _cle_tri(resultat: ResultatRecherche, tri: TriRecherche) -> tuple[int | str, ...]:
    """Clé de tri locale, utilisée pour réordonner après fusion des passes de filtre."""
    if tri is TriRecherche.MENTIONS:
        return (resultat.mentions or 0,)
    if tri is TriRecherche.TENDANCE:
        return (resultat.tendance or 0,)
    if tri in (TriRecherche.MODIFICATION, TriRecherche.CREATION):
        return (resultat.modifie_le or "",)
    return (resultat.telechargements or 0,)


def _fusionner(flux: Iterable[InfoDepotHF]) -> list[ResultatRecherche]:
    """Convertit et déduplique les dépôts issus de plusieurs passes de filtre."""
    vus: set[str] = set()
    resultats: list[ResultatRecherche] = []
    for info in flux:
        if info.id in vus:
            continue
        vus.add(info.id)
        resultats.append(_convertir(info))
    return resultats


def rechercher(
    requete: str,
    *,
    formats: Iterable[FormatRecherche] = (),
    tri: TriRecherche = TriRecherche.TELECHARGEMENTS,
    ordre: Ordre = "desc",
    page: int = 0,
    taille_page: int = 20,
) -> PageRecherche:
    """Cherche des dépôts sur le Hub et rend une page de résultats exploitables.

    Le Hub ne pagine pas côté serveur pour ce point d'entrée : on lit `(page + 1) × taille` entrées
    et on découpe. Le coût est assumé et borné par `LIMITE_RESULTATS_BRUTS`.
    """
    taille_page = max(1, min(taille_page, TAILLE_PAGE_MAX))
    page = max(0, page)
    limite = min((page + 1) * taille_page + MARGE_PAGINATION, LIMITE_RESULTATS_BRUTS)

    etiquettes: list[str | None] = [format_.value for format_ in formats] or [None]
    bruts: list[InfoDepotHF] = []
    for etiquette in etiquettes:
        bruts.extend(_lister(requete, etiquette, tri, limite))

    resultats = _fusionner(bruts)
    resultats.sort(key=lambda item: _cle_tri(item, tri), reverse=ordre == "desc")

    debut = page * taille_page
    tranche = resultats[debut : debut + taille_page]
    logger.debug("Recherche « {} » : {} dépôts retenus, page {}", requete, len(resultats), page)
    return PageRecherche(
        resultats=tranche,
        page=page,
        taille_page=taille_page,
        fin_atteinte=debut + taille_page >= len(resultats),
    )


def _fiche(depot: str, revision: str = "main") -> InfoDepotHF:
    """Fiche brute d'un dépôt, tailles de fichiers comprises."""
    try:
        return _api().model_info(depot, revision=revision, files_metadata=True)
    except Exception as exc:  # noqa: BLE001 — frontière externe, cf. `_echec`
        raise _echec(f"la lecture du dépôt {depot}", exc, depot=depot) from exc


def details(depot: str) -> ResultatRecherche:
    """Fiche complète d'un dépôt, avec la taille réelle de chaque fichier annoncée par le Hub."""
    return _convertir(_fiche(depot))


def inventaire(depot: str, revision: str = "main") -> list[FichierDepot]:
    """Tous les fichiers du dépôt avec leur taille annoncée.

    Sert au téléchargement : c'est ce qui permet d'annoncer un total honnête et de décider quoi
    écarter, à partir de la liste réelle des fichiers plutôt que d'un motif posé à l'aveugle.
    """
    info = _fiche(depot, revision)
    return [
        FichierDepot(
            nom=jumeau.rfilename,
            taille_octets=getattr(jumeau, "size", None),
            etiquette=etiquette_quantification(jumeau.rfilename),
        )
        for jumeau in info.siblings or []
    ]
