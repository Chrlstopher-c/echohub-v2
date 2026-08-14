"""Lecteur d'en-tête GGUF — lecture binaire brute, aucune interprétation.

Disposition du fichier (petit-boutiste) :

    magic 'GGUF' | version:u32 | nb_tenseurs:u64 | nb_cles:u64
    nb_cles fois       [longueur:u64][clé][type:u32][valeur]
    nb_tenseurs fois   [nom][n_dims:u32][dims:u64 × n_dims][type_ggml:u32][offset:u64]
    alignement, puis les données des tenseurs

En version 1 du format, compteurs et longueurs tiennent sur 32 bits ; à partir de la v2 ils sont
sur 64. La largeur est donc portée par le lecteur, pas codée en dur.

Ce module ne déduit rien et n'estime rien : il rend ce qui est écrit. L'interprétation
(architecture, nombre de blocs, quantification) revient à `gguf_metadata`. Toute lecture est bornée
— un fichier corrompu annonçant une chaîne de 10^18 octets doit produire une erreur explicite, pas
une allocation.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO, TypeAlias

from loguru import logger
from pydantic import BaseModel

from backend.core.errors import MetadonneesIllisibles
from backend.models.gguf_types import FORMATS_SCALAIRES, TypeValeurGGUF, taille_scalaire

MAGIC_GGUF = b"GGUF"
VERSIONS_SUPPORTEES = (1, 2, 3)
ALIGNEMENT_PAR_DEFAUT = 32

# Bornes de sûreté. Aucune n'est un réglage : ce sont des majorants au-delà desquels le fichier est
# nécessairement corrompu ou n'est pas un GGUF de modèle de langage.
LIMITE_CLES = 8_192
LIMITE_TENSEURS = 200_000
LIMITE_DIMENSIONS = 8
LIMITE_OCTETS_CHAINE = 1 << 20  # 1 Mio — un gabarit de chat peut peser plus de 100 Kio
LIMITE_ELEMENTS_TABLEAU = 1 << 24

# Au-delà de ces longueurs, un tableau est résumé au lieu d'être conservé : `tokenizer.ggml.tokens`
# porte des centaines de milliers de chaînes dont aucune n'intéresse le planificateur, seul son
# cardinal compte (taille du vocabulaire).
SEUIL_TABLEAU_CHAINES = 64
SEUIL_TABLEAU_NUMERIQUE = 4_096


class TableauResume(BaseModel):
    """Tableau volontairement non conservé : seule sa longueur a été retenue."""

    type_element: int
    longueur: int
    tronque: bool = True


ValeurGGUF: TypeAlias = (
    str | int | float | bool | list[str] | list[int] | list[float] | list[bool] | TableauResume
)


class InfoTenseur(BaseModel):
    """Descripteur d'un tenseur tel qu'écrit dans l'en-tête — nom, forme, type, position."""

    nom: str
    dimensions: tuple[int, ...]
    type_ggml: int
    offset_octets: int

    @property
    def nb_elements(self) -> int:
        """Nombre d'éléments du tenseur, produit de ses dimensions."""
        total = 1
        for dimension in self.dimensions:
            total *= dimension
        return total


class EnTeteGGUF(BaseModel):
    """Contenu intégral de l'en-tête d'un fichier GGUF, sans interprétation."""

    chemin: str
    version: int
    nb_tenseurs_declares: int
    nb_cles_declarees: int
    cles: dict[str, ValeurGGUF]
    tenseurs: list[InfoTenseur]
    alignement: int
    offset_donnees: int
    taille_fichier_octets: int


class _Flux:
    """Lecture séquentielle bornée sur un fichier GGUF ouvert en binaire."""

    def __init__(self, fichier: BinaryIO, chemin: Path) -> None:
        self._fichier = fichier
        self._chemin = chemin
        # Largeur des compteurs et longueurs : 4 octets en GGUF v1, 8 à partir de la v2.
        self.largeur_taille = 8

    def echouer(self, raison: str) -> MetadonneesIllisibles:
        """Construit l'erreur de lecture — jamais levée ailleurs qu'ici, message uniforme."""
        return MetadonneesIllisibles(
            f"En-tête GGUF illisible ({self._chemin.name}) : {raison}",
            details={"chemin": str(self._chemin), "position": self._fichier.tell()},
        )

    def octets(self, nombre: int) -> bytes:
        """Lit exactement `nombre` octets ; une lecture courte signifie un fichier tronqué."""
        if nombre < 0:
            raise self.echouer(f"longueur négative demandée ({nombre})")
        donnees = self._fichier.read(nombre)
        if len(donnees) != nombre:
            raise self.echouer(f"fichier tronqué, {nombre} octets attendus, {len(donnees)} lus")
        return donnees

    def sauter(self, nombre: int) -> None:
        """Avance de `nombre` octets sans les matérialiser en mémoire."""
        if nombre < 0:
            raise self.echouer(f"saut négatif demandé ({nombre})")
        self._fichier.seek(nombre, 1)

    def position(self) -> int:
        return self._fichier.tell()

    def scalaire(self, format_struct: str) -> int | float | bool:
        """Décode un scalaire au format `struct` donné."""
        taille = struct.calcsize(format_struct)
        return struct.unpack(format_struct, self.octets(taille))[0]

    def u32(self) -> int:
        return int(self.scalaire("<I"))

    def taille(self) -> int:
        """Compteur ou longueur, dans la largeur imposée par la version du format."""
        return int(self.scalaire("<I" if self.largeur_taille == 4 else "<Q"))

    def chaine(self) -> str:
        """Chaîne GGUF : longueur puis octets UTF-8."""
        longueur = self.taille()
        if longueur > LIMITE_OCTETS_CHAINE:
            raise self.echouer(f"chaîne de {longueur} octets, au-delà de la borne {LIMITE_OCTETS_CHAINE}")
        return self.octets(longueur).decode("utf-8", errors="replace")


def _type_valeur(flux: _Flux) -> TypeValeurGGUF:
    """Décode un identifiant de type ; un type inconnu rend la suite du flux indéchiffrable."""
    brut = flux.u32()
    try:
        return TypeValeurGGUF(brut)
    except ValueError as exc:
        # Sans la taille de la valeur, impossible de savoir combien d'octets sauter : on s'arrête.
        raise flux.echouer(f"type de valeur inconnu ({brut}), le reste de l'en-tête est indéchiffrable") from exc


def _lire_tableau(flux: _Flux) -> list[str] | list[int] | list[float] | list[bool] | TableauResume:
    """Lit un tableau homogène, ou le résume si sa longueur dépasse le seuil de conservation."""
    type_element = _type_valeur(flux)
    longueur = flux.taille()
    if longueur > LIMITE_ELEMENTS_TABLEAU:
        raise flux.echouer(f"tableau de {longueur} éléments, au-delà de la borne {LIMITE_ELEMENTS_TABLEAU}")

    if type_element is TypeValeurGGUF.ARRAY:
        raise flux.echouer("tableau de tableaux : disposition non prise en charge")
    if type_element is TypeValeurGGUF.STRING:
        return _lire_tableau_chaines(flux, longueur)
    return _lire_tableau_numerique(flux, type_element, longueur)


def _lire_tableau_chaines(flux: _Flux, longueur: int) -> list[str] | TableauResume:
    """Les chaînes sont de longueur variable : les sauter impose de les parcourir une à une."""
    conserver = longueur <= SEUIL_TABLEAU_CHAINES
    valeurs: list[str] = []
    for _ in range(longueur):
        chaine = flux.chaine()
        if conserver:
            valeurs.append(chaine)
    if conserver:
        return valeurs
    return TableauResume(type_element=int(TypeValeurGGUF.STRING), longueur=longueur)


def _lire_tableau_numerique(
    flux: _Flux, type_element: TypeValeurGGUF, longueur: int
) -> list[int] | list[float] | list[bool] | TableauResume:
    """Éléments de taille fixe : un tableau trop long se saute d'un seul déplacement."""
    format_struct = FORMATS_SCALAIRES[type_element]
    octets_element = taille_scalaire(type_element) or struct.calcsize(format_struct)

    if longueur > SEUIL_TABLEAU_NUMERIQUE:
        flux.sauter(longueur * octets_element)
        return TableauResume(type_element=int(type_element), longueur=longueur)

    brut = flux.octets(longueur * octets_element)
    # `struct.unpack` rend un tuple hétérogène pour le vérificateur de types alors que le tableau
    # GGUF est homogène par construction : la conversion est sûre, l'ignore documente pourquoi.
    decodes: tuple[object, ...] = struct.unpack(f"<{longueur}{format_struct[1:]}", brut)
    return list(decodes)  # type: ignore[return-value]


def _lire_valeur(flux: _Flux) -> ValeurGGUF:
    """Lit une valeur de métadonnée, quel que soit son type."""
    type_valeur = _type_valeur(flux)
    if type_valeur is TypeValeurGGUF.STRING:
        return flux.chaine()
    if type_valeur is TypeValeurGGUF.ARRAY:
        return _lire_tableau(flux)
    return flux.scalaire(FORMATS_SCALAIRES[type_valeur])


def _lire_cles(flux: _Flux, nombre: int) -> dict[str, ValeurGGUF]:
    """Lit les `nombre` paires clé/valeur annoncées par l'en-tête."""
    if nombre > LIMITE_CLES:
        raise flux.echouer(f"{nombre} clés annoncées, au-delà de la borne {LIMITE_CLES}")
    cles: dict[str, ValeurGGUF] = {}
    for _ in range(nombre):
        cle = flux.chaine()
        cles[cle] = _lire_valeur(flux)
    return cles


def _lire_tenseurs(flux: _Flux, nombre: int) -> list[InfoTenseur]:
    """Lit les `nombre` descripteurs de tenseurs annoncés par l'en-tête."""
    if nombre > LIMITE_TENSEURS:
        raise flux.echouer(f"{nombre} tenseurs annoncés, au-delà de la borne {LIMITE_TENSEURS}")
    tenseurs: list[InfoTenseur] = []
    for _ in range(nombre):
        nom = flux.chaine()
        nb_dimensions = flux.u32()
        if nb_dimensions > LIMITE_DIMENSIONS:
            raise flux.echouer(f"tenseur '{nom}' à {nb_dimensions} dimensions, au-delà de {LIMITE_DIMENSIONS}")
        dimensions = tuple(flux.taille() for _ in range(nb_dimensions))
        type_ggml = flux.u32()
        offset = int(flux.scalaire("<Q"))
        tenseurs.append(InfoTenseur(nom=nom, dimensions=dimensions, type_ggml=type_ggml, offset_octets=offset))
    return tenseurs


def _alignement(cles: dict[str, ValeurGGUF]) -> int:
    """`general.alignment` s'il est présent et exploitable, sinon la valeur par défaut du format."""
    valeur = cles.get("general.alignment")
    if isinstance(valeur, int) and not isinstance(valeur, bool) and valeur > 0:
        return valeur
    return ALIGNEMENT_PAR_DEFAUT


def _valider_prefixe(flux: _Flux) -> int:
    """Vérifie le magic, rend la version et cale la largeur des compteurs."""
    magic = flux.octets(4)
    if magic != MAGIC_GGUF:
        raise flux.echouer(f"magic {magic!r} au lieu de {MAGIC_GGUF!r} — ce n'est pas un fichier GGUF")
    version = flux.u32()
    if version not in VERSIONS_SUPPORTEES:
        raise flux.echouer(f"version {version} non prise en charge (versions connues : {VERSIONS_SUPPORTEES})")
    flux.largeur_taille = 4 if version == 1 else 8
    return version


def lire_entete(chemin: Path | str, *, avec_tenseurs: bool = True) -> EnTeteGGUF:
    """Lit l'en-tête complet d'un fichier GGUF.

    `avec_tenseurs=False` s'arrête après les métadonnées : suffisant pour connaître l'architecture
    et le nombre de blocs, sans parcourir des centaines de descripteurs.
    """
    chemin = Path(chemin)
    try:
        taille_fichier = chemin.stat().st_size
    except OSError as exc:
        logger.error("Fichier GGUF inaccessible {} : {}", chemin, exc)
        raise MetadonneesIllisibles(
            f"Fichier GGUF inaccessible : {chemin.name}",
            details={"chemin": str(chemin), "cause": str(exc)},
        ) from exc

    try:
        with chemin.open("rb") as fichier:
            return _lire_flux(fichier, chemin, taille_fichier, avec_tenseurs=avec_tenseurs)
    except OSError as exc:
        logger.error("Lecture de l'en-tête GGUF échouée {} : {}", chemin, exc)
        raise MetadonneesIllisibles(
            f"Lecture de l'en-tête GGUF impossible : {chemin.name}",
            details={"chemin": str(chemin), "cause": str(exc)},
        ) from exc


def _lire_flux(fichier: BinaryIO, chemin: Path, taille_fichier: int, *, avec_tenseurs: bool) -> EnTeteGGUF:
    """Corps de la lecture, séparé pour garder `lire_entete` centré sur la gestion d'erreurs."""
    flux = _Flux(fichier, chemin)
    version = _valider_prefixe(flux)
    nb_tenseurs = flux.taille()
    nb_cles = flux.taille()

    cles = _lire_cles(flux, nb_cles)
    tenseurs = _lire_tenseurs(flux, nb_tenseurs) if avec_tenseurs else []

    alignement = _alignement(cles)
    position = flux.position()
    # Les données de tenseurs commencent au premier multiple de l'alignement après les descripteurs.
    offset_donnees = -(-position // alignement) * alignement if avec_tenseurs else 0

    logger.debug("En-tête GGUF lu : {} ({} clés, {} tenseurs)", chemin.name, len(cles), len(tenseurs))
    return EnTeteGGUF(
        chemin=str(chemin),
        version=version,
        nb_tenseurs_declares=nb_tenseurs,
        nb_cles_declarees=nb_cles,
        cles=cles,
        tenseurs=tenseurs,
        alignement=alignement,
        offset_donnees=offset_donnees,
        taille_fichier_octets=taille_fichier,
    )
