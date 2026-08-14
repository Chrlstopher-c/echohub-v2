"""Interprétation des métadonnées GGUF — ce que le fichier dit de lui-même, rien d'autre.

Ce module est la raison d'être du domaine. Il répond aux questions dont dépend tout le
planificateur : quelle architecture, **combien de blocs**, combien d'experts, quel contexte natif,
quelle quantification, et surtout **combien pèse réellement un bloc**.

Deux interdits, tous deux payés en défauts mesurés sur la v1 :

- rien n'est déduit du nom du fichier ni du nombre de paramètres. La v1 rangeait les modèles par
  paliers de taille et annonçait 80 couches pour un modèle qui en a 41 ;
- rien n'est estimé par un facteur. La v1 supposait 150 Mo par couche là où la mesure donne 436 Mo.

Quand une information n'est pas dans le fichier, le champ vaut `None`. Un `None` se traite en aval,
une estimation fausse ne se voit pas.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

from backend.core.errors import MetadonneesIllisibles
from backend.models.gguf_reader import EnTeteGGUF, InfoTenseur, TableauResume, ValeurGGUF, lire_entete
from backend.models.gguf_types import nom_ftype, traits_ggml

PREFIXE_BLOC = "blk."

SourceBlockCount = Literal["cle_gguf", "index_des_tenseurs"]


class ParametresAttention(BaseModel):
    """Ce dont le dimensionnement du cache KV dépend. Tous facultatifs : lus ou absents."""

    nb_tetes: int | None = None
    nb_tetes_kv: int | None = None
    # Certaines architectures déclarent un nombre de têtes KV par bloc plutôt qu'une valeur unique.
    nb_tetes_kv_par_bloc: list[int] | None = None
    dimension_cle: int | None = None
    dimension_valeur: int | None = None
    dimension_rope: int | None = None
    base_rope: float | None = None


class MesuresTenseurs(BaseModel):
    """Poids réel des tenseurs, calculé descripteur par descripteur.

    `octets_par_bloc` est la réponse directe au défaut le plus coûteux de la v1 : 150 Mo par couche
    supposés, 436 Mo réels sur Qwen3.6-35B-A3B. La liste est ordonnée par index de bloc.
    """

    octets_par_bloc: list[int]
    octets_hors_blocs: int = Field(ge=0)
    octets_totaux: int = Field(ge=0)
    blocs_observes: int = Field(ge=0)
    # Un type ggml absent des tables rend le total incomplet : on le dit au lieu de l'arrondir.
    types_ggml_inconnus: list[int] = Field(default_factory=list)

    @property
    def complet(self) -> bool:
        """Vrai si aucun tenseur n'a échappé au calcul de taille."""
        return not self.types_ggml_inconnus


class MetadonneesGGUF(BaseModel):
    """Tout ce qu'un fichier GGUF déclare, lu et non deviné."""

    chemin: str
    taille_fichier_octets: int
    version_gguf: int
    architecture: str
    nom: str | None = None

    block_count: int = Field(ge=0)
    source_block_count: SourceBlockCount
    contexte_natif: int | None = None
    longueur_embedding: int | None = None
    longueur_feed_forward: int | None = None

    nb_experts: int | None = None
    nb_experts_actifs: int | None = None

    attention: ParametresAttention = Field(default_factory=ParametresAttention)

    # Déclarée à l'export (`general.file_type`) vs relevée dans les descripteurs de tenseurs. Les
    # deux sont exposées : un écart entre elles est en soi une information.
    quantification_declaree: str | None = None
    quantification_mesuree: str | None = None

    nb_tenseurs: int = Field(ge=0)
    taille_vocabulaire: int | None = None
    mesures: MesuresTenseurs | None = None

    @property
    def est_moe(self) -> bool:
        """Mélange d'experts dès qu'au moins deux experts sont déclarés."""
        return bool(self.nb_experts and self.nb_experts > 1)


def _entier(cles: dict[str, ValeurGGUF], cle: str) -> int | None:
    """Entier associé à une clé, ou `None` si absente ou d'un autre type."""
    valeur = cles.get(cle)
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        return None
    return valeur


def _reel(cles: dict[str, ValeurGGUF], cle: str) -> float | None:
    valeur = cles.get(cle)
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    return float(valeur)


def _chaine(cles: dict[str, ValeurGGUF], cle: str) -> str | None:
    valeur = cles.get(cle)
    return valeur if isinstance(valeur, str) else None


def _entiers(cles: dict[str, ValeurGGUF], cle: str) -> list[int] | None:
    valeur = cles.get(cle)
    if not isinstance(valeur, list) or not valeur:
        return None
    if not all(isinstance(element, int) and not isinstance(element, bool) for element in valeur):
        return None
    return [int(element) for element in valeur]


def _index_bloc(nom_tenseur: str) -> int | None:
    """Index du bloc auquel appartient un tenseur (`blk.12.attn_q.weight` -> 12), sinon `None`."""
    if not nom_tenseur.startswith(PREFIXE_BLOC):
        return None
    reste = nom_tenseur[len(PREFIXE_BLOC) :]
    index, _, suite = reste.partition(".")
    return int(index) if suite and index.isdigit() else None


def _attention(cles: dict[str, ValeurGGUF], architecture: str) -> ParametresAttention:
    """Paramètres d'attention de l'architecture, tels qu'écrits."""
    prefixe = f"{architecture}.attention."
    tetes_kv = _entier(cles, f"{prefixe}head_count_kv")
    return ParametresAttention(
        nb_tetes=_entier(cles, f"{prefixe}head_count"),
        nb_tetes_kv=tetes_kv,
        nb_tetes_kv_par_bloc=None if tetes_kv is not None else _entiers(cles, f"{prefixe}head_count_kv"),
        dimension_cle=_entier(cles, f"{prefixe}key_length"),
        dimension_valeur=_entier(cles, f"{prefixe}value_length"),
        dimension_rope=_entier(cles, f"{architecture}.rope.dimension_count"),
        base_rope=_reel(cles, f"{architecture}.rope.freq_base"),
    )


def _taille_vocabulaire(cles: dict[str, ValeurGGUF], architecture: str) -> int | None:
    """Cardinal du vocabulaire : la clé dédiée si elle existe, sinon la longueur du tableau lu."""
    declare = _entier(cles, f"{architecture}.vocab_size")
    if declare is not None:
        return declare
    jetons = cles.get("tokenizer.ggml.tokens")
    if isinstance(jetons, TableauResume):
        return jetons.longueur
    return len(jetons) if isinstance(jetons, list) else None


def _mesurer_tenseurs(tenseurs: list[InfoTenseur]) -> MesuresTenseurs | None:
    """Somme les octets réellement occupés, bloc par bloc, à partir des types et des formes."""
    if not tenseurs:
        return None

    par_bloc: dict[int, int] = {}
    hors_blocs = 0
    inconnus: set[int] = set()

    for tenseur in tenseurs:
        traits = traits_ggml(tenseur.type_ggml)
        if traits is None:
            inconnus.add(tenseur.type_ggml)
            continue
        octets = traits.octets(tenseur.nb_elements)
        index = _index_bloc(tenseur.nom)
        if index is None:
            hors_blocs += octets
        else:
            par_bloc[index] = par_bloc.get(index, 0) + octets

    ordonnes = [par_bloc[index] for index in sorted(par_bloc)]
    return MesuresTenseurs(
        octets_par_bloc=ordonnes,
        octets_hors_blocs=hors_blocs,
        octets_totaux=hors_blocs + sum(ordonnes),
        blocs_observes=len(par_bloc),
        types_ggml_inconnus=sorted(inconnus),
    )


def _quantification_mesuree(tenseurs: list[InfoTenseur]) -> str | None:
    """Type ggml dominant parmi les tenseurs de blocs, pondéré par le nombre d'éléments.

    Les tenseurs hors blocs (embeddings, sortie) sont écartés : ils sont souvent laissés dans une
    précision supérieure et fausseraient la lecture de la quantification du corps du modèle.
    """
    poids: Counter[int] = Counter()
    for tenseur in tenseurs:
        if _index_bloc(tenseur.nom) is not None:
            poids[tenseur.type_ggml] += tenseur.nb_elements
    if not poids:
        return None
    dominant = poids.most_common(1)[0][0]
    traits = traits_ggml(dominant)
    return traits.nom if traits else f"type_ggml_{dominant}"


def indices_de_blocs(tenseurs: list[InfoTenseur]) -> set[int]:
    """Ensemble des index de blocs effectivement présents dans les descripteurs de tenseurs."""
    indices = (_index_bloc(tenseur.nom) for tenseur in tenseurs)
    return {index for index in indices if index is not None}


def _resoudre_block_count(
    cles: dict[str, ValeurGGUF],
    architecture: str,
    tenseurs: list[InfoTenseur],
) -> tuple[int, SourceBlockCount]:
    """Nombre de blocs : la clé du fichier, sinon le plus grand index de bloc observé, sinon erreur.

    Les deux sources sont des lectures du fichier. Aucune ne dérive du nom ni du nombre de
    paramètres — c'est précisément l'inférence qui a produit « 80 couches » pour un modèle à 41.
    """
    declare = _entier(cles, f"{architecture}.block_count")
    if declare is not None:
        return declare, "cle_gguf"

    indices = indices_de_blocs(tenseurs)
    if indices:
        logger.warning("`{}.block_count` absent : nombre de blocs relevé sur les tenseurs", architecture)
        return max(indices) + 1, "index_des_tenseurs"

    raise MetadonneesIllisibles(
        f"Nombre de blocs introuvable : ni `{architecture}.block_count` ni tenseur `blk.N.*`.",
        remediation="Le fichier n'est pas un modèle GGUF exploitable : retélécharger ou changer de variante.",
        details={"architecture": architecture},
    )


def depuis_entete(entete: EnTeteGGUF) -> MetadonneesGGUF:
    """Interprète un en-tête déjà lu. Point d'entrée testable sans fichier ni GPU."""
    architecture = _chaine(entete.cles, "general.architecture")
    if not architecture:
        raise MetadonneesIllisibles(
            "`general.architecture` absent de l'en-tête GGUF.",
            remediation="Le fichier est incomplet ou n'est pas un modèle : relancer le téléchargement.",
            details={"chemin": entete.chemin},
        )

    block_count, source = _resoudre_block_count(entete.cles, architecture, entete.tenseurs)
    ftype = _entier(entete.cles, "general.file_type")

    return MetadonneesGGUF(
        chemin=entete.chemin,
        taille_fichier_octets=entete.taille_fichier_octets,
        version_gguf=entete.version,
        architecture=architecture,
        nom=_chaine(entete.cles, "general.name"),
        block_count=block_count,
        source_block_count=source,
        contexte_natif=_entier(entete.cles, f"{architecture}.context_length"),
        longueur_embedding=_entier(entete.cles, f"{architecture}.embedding_length"),
        longueur_feed_forward=_entier(entete.cles, f"{architecture}.feed_forward_length"),
        nb_experts=_entier(entete.cles, f"{architecture}.expert_count"),
        nb_experts_actifs=_entier(entete.cles, f"{architecture}.expert_used_count"),
        attention=_attention(entete.cles, architecture),
        quantification_declaree=nom_ftype(ftype) if ftype is not None else None,
        quantification_mesuree=_quantification_mesuree(entete.tenseurs),
        nb_tenseurs=entete.nb_tenseurs_declares,
        taille_vocabulaire=_taille_vocabulaire(entete.cles, architecture),
        mesures=_mesurer_tenseurs(entete.tenseurs),
    )


def lire_metadonnees(chemin: Path | str) -> MetadonneesGGUF:
    """Lit un fichier GGUF et en rend les métadonnées interprétées."""
    metadonnees = depuis_entete(lire_entete(chemin))
    logger.info(
        "GGUF lu : {} — architecture {}, {} blocs ({}), quantification {}",
        Path(metadonnees.chemin).name,
        metadonnees.architecture,
        metadonnees.block_count,
        metadonnees.source_block_count,
        metadonnees.quantification_mesuree or metadonnees.quantification_declaree or "inconnue",
    )
    return metadonnees
