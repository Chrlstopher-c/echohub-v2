"""Capacités d'un modèle — ce que son dépôt **laisse entendre**, jamais ce qui a été vérifié.

Un utilisateur cherche « un modèle qui voit des images » ou « un modèle qui appelle des outils ».
Le Hub ne répond pas à cette question : il publie des étiquettes libres, un `pipeline_tag`, un nom
de dépôt et une liste de fichiers. Ce module transforme ces déclarations en un vocabulaire fermé et
filtrable, **en assumant l'inférence et en la traçant**.

Trois règles, toutes issues du défaut central de la v1 (calculer des faits à partir d'un nom) :

1. **Rien ici n'est une mesure.** Le champ produit s'appelle `capacites_deduites` et chaque entrée
   porte les indices qui l'ont fait conclure. L'interface ne peut donc pas l'afficher comme un fait
   vérifié sans mentir explicitement.
2. **L'absence d'indice vaut absence de capacité connue**, jamais absence de capacité. Une liste
   vide veut dire « le dépôt n'annonce rien », pas « le modèle ne sait pas faire ».
3. **La provenance est publiée.** `IndiceCapacite` nomme la source (étiquette, tâche, nom du dépôt,
   description, fichier) et la valeur exacte qui a déclenché la conclusion.

Le module est pur : aucune entrée/sortie, aucun réseau. Il prend `SignauxDepot` et rend des
déductions, ce qui le rend testable sans le Hub — c'est la condition pour que ses règles soient
vérifiables plutôt que crues sur parole.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field


class Capacite(str, Enum):
    """Vocabulaire fermé des capacités filtrables. Les valeurs voyagent telles quelles en HTTP."""

    RAISONNEMENT = "raisonnement"
    APPEL_OUTILS = "appel_outils"
    VISION = "vision"
    GENERATION_IMAGE = "generation_image"
    AUDIO_ENTREE = "audio_entree"
    AUDIO_SORTIE = "audio_sortie"
    CODE = "code"
    EMBEDDINGS = "embeddings"
    SANS_CENSURE = "sans_censure"


class SourceIndice(str, Enum):
    """D'où vient un indice. Toutes ces sources sont déclaratives, aucune n'est une lecture de poids."""

    TACHE = "tache"
    ETIQUETTE = "etiquette"
    NOM = "nom"
    DESCRIPTION = "description"
    FICHIER = "fichier"


class IndiceCapacite(BaseModel):
    """Ce qui a fait conclure à une capacité : la source, et la valeur exacte qui a correspondu."""

    source: SourceIndice
    valeur: str


class CapaciteDeduite(BaseModel):
    """Une capacité et la totalité de ce qui plaide pour elle.

    `indices` n'est jamais vide : une capacité sans indice n'est pas déduite, elle est absente.
    """

    capacite: Capacite
    indices: list[IndiceCapacite] = Field(min_length=1)


class DefinitionCapacite(BaseModel):
    """Sens d'une capacité, publié avec elle pour que l'interface n'ait pas à le réécrire."""

    capacite: Capacite
    libelle: str
    definition: str


class SignauxDepot(BaseModel):
    """Tout ce qu'un dépôt déclare de lui-même, et rien d'autre : la seule matière de la déduction.

    Structure volontairement détachée de `huggingface_hub` : la déduction se teste avec des jeux
    d'étiquettes en dur, sans qu'un changement de la bibliothèque puisse rendre les tests muets.
    """

    depot: str = ""
    tache: str | None = None
    etiquettes: list[str] = Field(default_factory=list)
    fichiers: list[str] = Field(default_factory=list)
    description: str | None = None


# Définitions écrites de chaque capacité — (libellé court, définition). L'ordre du dictionnaire est
# l'ordre d'affichage et l'ordre de déduction : Python garantit l'ordre d'insertion, ce qui rend la
# sortie déterministe sans tri supplémentaire.
_TEXTES: dict[Capacite, tuple[str, str]] = {
    Capacite.RAISONNEMENT: (
        "Raisonnement",
        "Le dépôt annonce un modèle qui produit une trace de réflexion avant sa réponse : des jetons "
        "de « thinking » sont consommés avant le premier mot utile, ce qui change le budget de sortie "
        "à prévoir.",
    ),
    Capacite.APPEL_OUTILS: (
        "Appel d'outils",
        "Le dépôt annonce un modèle entraîné à émettre des appels de fonctions structurés à partir "
        "d'un catalogue d'outils fourni dans l'invite.",
    ),
    Capacite.VISION: (
        "Vision",
        "Le dépôt annonce un modèle qui accepte des images en entrée. En GGUF, la présence d'un "
        "projecteur `mmproj` est le signe le plus tangible — c'est un fichier réellement listé, pas "
        "une lecture de son contenu.",
    ),
    Capacite.GENERATION_IMAGE: (
        "Génération d'images",
        "Le dépôt annonce un modèle qui produit des images. Aucun moteur du MVP ne sait le charger : "
        "le filtre sert à reconnaître ces dépôts, pas à promettre de les servir.",
    ),
    Capacite.AUDIO_ENTREE: (
        "Écoute audio",
        "Le dépôt annonce un modèle qui accepte un signal sonore en entrée — transcription, "
        "classification, parole vers texte.",
    ),
    Capacite.AUDIO_SORTIE: (
        "Synthèse vocale",
        "Le dépôt annonce un modèle qui produit un signal sonore : synthèse de parole ou clonage "
        "de voix.",
    ),
    Capacite.CODE: (
        "Code",
        "Le dépôt annonce une spécialisation sur le code source — génération, complétion ou "
        "compréhension de programmes.",
    ),
    Capacite.EMBEDDINGS: (
        "Embeddings",
        "Le dépôt annonce un modèle qui produit des vecteurs de représentation plutôt que du texte : "
        "il ne répond pas à une conversation.",
    ),
    Capacite.SANS_CENSURE: (
        "Sans censure",
        "Le dépôt annonce un modèle dont l'alignement a été retiré ou contourné (« uncensored », "
        "« abliterated »). C'est une déclaration de l'auteur, jamais une vérification de comportement.",
    ),
}


@dataclass(frozen=True, slots=True)
class ReglesCapacite:
    """Signaux qui font conclure à une capacité. Ils sont alternatifs : un seul suffit.

    `motif_texte` s'applique au nom du dépôt ET à sa description, qui sont deux textes libres de la
    même nature. Il porte un unique groupe capturant, dont le contenu devient la valeur de l'indice :
    la provenance montre le fragment qui a conclu, pas la chaîne entière.
    """

    taches: frozenset[str] = frozenset()
    etiquettes: frozenset[str] = frozenset()
    motif_texte: re.Pattern[str] | None = None
    motif_fichier: re.Pattern[str] | None = None


REGLES: dict[Capacite, ReglesCapacite] = {
    Capacite.RAISONNEMENT: ReglesCapacite(
        etiquettes=frozenset({"reasoning", "thinking", "chain-of-thought", "cot", "reasoning-model"}),
        motif_texte=re.compile(r"\b(thinking|reasoning|cot|qwq|deepseek-r1|r1-distill)\b"),
    ),
    Capacite.APPEL_OUTILS: ReglesCapacite(
        etiquettes=frozenset({"function-calling", "tool-calling", "tool-use", "tools", "agentic"}),
        motif_texte=re.compile(r"\b(function-calling|tool-calling|tool-use|toolcall)\b"),
    ),
    Capacite.VISION: ReglesCapacite(
        taches=frozenset({"image-text-to-text", "visual-question-answering", "image-to-text", "video-text-to-text"}),
        etiquettes=frozenset({"vision", "multimodal", "vlm", "image-text-to-text", "vision-language"}),
        motif_texte=re.compile(r"\b(vision|vl|vlm|llava|multimodal|omni|internvl)\b"),
        # Un projecteur multimodal n'est pas le modèle, mais sa seule présence dans la liste des
        # fichiers dit que le dépôt embarque une tour de vision. C'est l'indice le plus tangible
        # disponible avant tout téléchargement.
        motif_fichier=re.compile(r"mmproj"),
    ),
    Capacite.GENERATION_IMAGE: ReglesCapacite(
        taches=frozenset({"text-to-image", "image-to-image", "unconditional-image-generation"}),
        etiquettes=frozenset({"text-to-image", "stable-diffusion", "diffusers", "sdxl", "image-generation"}),
        motif_texte=re.compile(r"\b(stable-diffusion|sdxl|text-to-image)\b"),
    ),
    Capacite.AUDIO_ENTREE: ReglesCapacite(
        taches=frozenset({"automatic-speech-recognition", "audio-classification", "audio-text-to-text"}),
        etiquettes=frozenset({"asr", "speech-recognition", "automatic-speech-recognition", "whisper"}),
        motif_texte=re.compile(r"\b(whisper|asr|speech-to-text|stt)\b"),
    ),
    Capacite.AUDIO_SORTIE: ReglesCapacite(
        taches=frozenset({"text-to-speech", "text-to-audio"}),
        etiquettes=frozenset({"tts", "text-to-speech", "speech-synthesis", "voice-cloning"}),
        motif_texte=re.compile(r"\b(tts|text-to-speech|speech-synthesis|xtts)\b"),
    ),
    Capacite.CODE: ReglesCapacite(
        etiquettes=frozenset({"code", "code-generation", "codegen", "programming"}),
        motif_texte=re.compile(r"\b(coder|code|codestral|starcoder|codellama|codegen)\b"),
    ),
    Capacite.EMBEDDINGS: ReglesCapacite(
        taches=frozenset({"feature-extraction", "sentence-similarity"}),
        etiquettes=frozenset({"sentence-transformers", "embeddings", "text-embeddings-inference"}),
        motif_texte=re.compile(r"\b(embeddings?|embed|bge-m3)\b"),
    ),
    Capacite.SANS_CENSURE: ReglesCapacite(
        etiquettes=frozenset({"uncensored", "abliterated", "not-for-all-audiences", "unaligned"}),
        motif_texte=re.compile(r"\b(uncensored|abliterated|unfiltered|unaligned)\b"),
    ),
}


def definitions() -> list[DefinitionCapacite]:
    """Vocabulaire complet, dans l'ordre d'affichage.

    Publié par l'API pour que le frontend compose ses filtres à partir d'une seule source : une liste
    de capacités recopiée côté interface finirait par diverger de celle qui filtre réellement.
    """
    return [
        DefinitionCapacite(capacite=capacite, libelle=libelle, definition=texte)
        for capacite, (libelle, texte) in _TEXTES.items()
    ]


def _normaliser(texte: str) -> str:
    """Minuscules et séparateurs unifiés sur le tiret.

    `_` est un caractère de mot pour `\\b` : sans cette translation, `Qwen3_VL` ne correspondrait pas
    au motif `\\bvl\\b` alors que `Qwen3-VL` correspondrait. Le point subit le même sort (`FLUX.1`).
    """
    return texte.lower().replace("_", "-").replace(".", "-")


def _nom_modele(depot: str) -> str:
    """Partie du dépôt qui nomme le modèle, sans l'auteur.

    L'auteur est écarté volontairement : un compte de reconditionnement (`mradermacher`, `bartowski`)
    publie tous les genres de modèles, son nom n'apprend rien sur celui-ci.
    """
    return depot.rsplit("/", 1)[-1]


def _par_tache(tache: str | None, regles: ReglesCapacite) -> list[IndiceCapacite]:
    """Indice tiré du `pipeline_tag` — la déclaration la plus structurée que le Hub propose."""
    if tache is None:
        return []
    normalisee = _normaliser(tache)
    if normalisee not in regles.taches:
        return []
    return [IndiceCapacite(source=SourceIndice.TACHE, valeur=normalisee)]


def _par_etiquettes(etiquettes: Iterable[str], regles: ReglesCapacite) -> list[IndiceCapacite]:
    """Indices tirés des étiquettes du dépôt, par correspondance exacte.

    Exacte et non par sous-chaîne : les étiquettes sont un vocabulaire déjà normalisé côté Hub, et
    une correspondance partielle ferait passer `not-for-all-audiences` pour de l'audio.
    """
    presentes = {_normaliser(etiquette) for etiquette in etiquettes}
    return [
        IndiceCapacite(source=SourceIndice.ETIQUETTE, valeur=etiquette)
        for etiquette in sorted(presentes & regles.etiquettes)
    ]


def _par_texte(source: SourceIndice, texte: str | None, regles: ReglesCapacite) -> list[IndiceCapacite]:
    """Indices tirés d'un texte libre (nom du dépôt, description), fragment correspondant à l'appui."""
    if texte is None or regles.motif_texte is None:
        return []
    fragments = sorted(set(regles.motif_texte.findall(_normaliser(texte))))
    return [IndiceCapacite(source=source, valeur=fragment) for fragment in fragments]


def _par_fichiers(fichiers: Iterable[str], regles: ReglesCapacite) -> list[IndiceCapacite]:
    """Indices tirés des fichiers listés par le dépôt. La valeur rendue est le nom du fichier.

    Le nom complet plutôt que le fragment : « mmproj-model-f16.gguf » est une justification lisible
    par un humain, « mmproj » ne l'est pas.
    """
    if regles.motif_fichier is None:
        return []
    correspondants = sorted({nom for nom in fichiers if regles.motif_fichier.search(_normaliser(nom))})
    return [IndiceCapacite(source=SourceIndice.FICHIER, valeur=nom) for nom in correspondants]


def _dedupliquer(indices: list[IndiceCapacite]) -> list[IndiceCapacite]:
    """Un couple (source, valeur) ne compte qu'une fois ; l'ordre de détection est conservé."""
    vus: set[tuple[str, str]] = set()
    uniques: list[IndiceCapacite] = []
    for indice in indices:
        cle = (indice.source.value, indice.valeur)
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append(indice)
    return uniques


def _indices(signaux: SignauxDepot, regles: ReglesCapacite) -> list[IndiceCapacite]:
    """Tout ce qui, dans ce dépôt, plaide pour la capacité décrite par `regles`."""
    trouves: list[IndiceCapacite] = []
    trouves.extend(_par_tache(signaux.tache, regles))
    trouves.extend(_par_etiquettes(signaux.etiquettes, regles))
    trouves.extend(_par_texte(SourceIndice.NOM, _nom_modele(signaux.depot), regles))
    trouves.extend(_par_texte(SourceIndice.DESCRIPTION, signaux.description, regles))
    trouves.extend(_par_fichiers(signaux.fichiers, regles))
    return _dedupliquer(trouves)


def deduire_capacites(signaux: SignauxDepot) -> list[CapaciteDeduite]:
    """Capacités que ce dépôt laisse entendre, chacune accompagnée de ses indices.

    Fonction pure et totale : elle ne consulte rien d'extérieur et ne lève pas. Une liste vide
    signifie « le dépôt n'annonce aucune capacité reconnue » — surtout pas « le modèle n'en a pas ».
    """
    return [
        CapaciteDeduite(capacite=capacite, indices=indices)
        for capacite, regles in REGLES.items()
        if (indices := _indices(signaux, regles))
    ]


def possede_toutes(deduites: Iterable[CapaciteDeduite], exigees: Iterable[Capacite]) -> bool:
    """Vrai si toutes les capacités exigées ont été déduites — combinaison ET du filtre de recherche.

    ET et non OU : demander « vision » et « appel d'outils » cherche un modèle qui fait les deux, ce
    qui est la seule lecture utile quand on choisit un modèle à charger.
    """
    presentes = {deduite.capacite for deduite in deduites}
    return all(capacite in presentes for capacite in exigees)
