"""Interprétation des métadonnées GGUF — ce que le fichier dit de lui-même, rien d'autre.

Ce module est la raison d'être du domaine. Il répond aux questions dont dépend tout le
planificateur : quelle architecture, **combien de blocs**, combien d'experts, quel contexte natif,
quelle quantification, **combien pèse réellement un bloc** et, sur un mélange d'experts, **quelle
part de ce poids est déportable** — les experts routés d'un côté, ce qui est lu à chaque token de
l'autre.

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
from pydantic import BaseModel, Field, model_validator

from backend.core.errors import MetadonneesIllisibles
from backend.models.gguf_reader import EnTeteGGUF, InfoTenseur, TableauResume, ValeurGGUF, lire_entete
from backend.models.gguf_types import est_tenseur_expert, nom_ftype, porte_attention, traits_ggml

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
    # Une couche sur `intervalle_attention_pleine` porte une attention pleine — 4 sur les deux
    # modèles de cette machine, soit 10 blocs d'attention sur 40 et 16 sur 64. Facturer le cache KV
    # sur la totalité des couches invente 1,9 Gio de VRAM à 32k de contexte et 3,3 Gio à 57k.
    intervalle_attention_pleine: int | None = None
    # `rope.dimension_sections` — découpe mRoPE ([11,11,10,0] relevé). Sans effet mémoire, mais sans
    # elle la caractérisation du RoPE affichée à l'utilisateur est incomplète.
    sections_rope: list[int] | None = None


class ParametresSSM(BaseModel):
    """État récurrent des architectures hybrides — ce qui remplace le cache KV là où l'attention est
    absente. Son coût est constant : il ne grandit pas avec le contexte. Tous facultatifs.
    """

    dimension_interne: int | None = None
    dimension_etat: int | None = None
    noyau_convolution: int | None = None
    # `ssm.time_step_rank` : coïncide avec le nombre de têtes SSM sur les deux modèles relevés
    # (formes `ssm_a` (32,) et `ssm_dt.bias` (32,)). Le champ porte le nom de la clé, pas celui de
    # l'interprétation — c'est l'appelant qui décide d'y voir des têtes.
    rang_pas_de_temps: int | None = None
    nb_groupes: int | None = None

    @property
    def declare(self) -> bool:
        """Vrai dès qu'une clé `ssm.*` a été lue : l'architecture porte un état récurrent."""
        return any(
            valeur is not None
            for valeur in (
                self.dimension_interne,
                self.dimension_etat,
                self.noyau_convolution,
                self.rang_pas_de_temps,
                self.nb_groupes,
            )
        )


class ParametresExperts(BaseModel):
    """Ce qu'un MoE déclare de son mélange, hors cardinal.

    `nb_experts` et `nb_experts_actifs` restent sur `MetadonneesGGUF` : ils y étaient avant cette
    lecture, ils gouvernent `est_moe` et des appelants les lisent déjà là. Les clés ajoutées ici sont
    celles qui manquaient au dimensionnement, à commencer par `expert_feed_forward_length` — dont
    l'absence de lecture faisait échouer la construction d'une cible de chargement.
    """

    # `{arch}.expert_feed_forward_length` : largeur FFN d'UN expert (512 relevé). Ce n'est PAS un
    # substitut de `feed_forward_length` : la largeur vive d'un token vaut cette valeur multipliée
    # par le nombre d'experts actifs. Confondre les deux sous-dimensionne d'un facteur 8.
    largeur_ffn_expert: int | None = None
    # `{arch}.expert_shared_feed_forward_length` : largeur totale de la branche partagée (512 relevé),
    # tenseurs `ffn_*_shexp`, actifs à chaque token — jamais déportables en mémoire hôte.
    largeur_ffn_partagee: int | None = None
    nb_experts_partages: int | None = None
    # Blocs denses en tête de modèle : changerait la répartition experts/dense par bloc. Non observée
    # sur les deux fichiers de la machine — lue si présente, `None` sinon, jamais défaut.
    nb_blocs_denses_en_tete: int | None = None
    fonction_routage: int | None = None
    echelle_poids: float | None = None
    poids_normalises: bool | None = None


class MesuresTenseurs(BaseModel):
    """Poids réel des tenseurs, calculé descripteur par descripteur.

    `octets_par_bloc` est la réponse directe au défaut le plus coûteux de la v1 : 150 Mo par couche
    supposés, 436 Mo réels sur Qwen3.6-35B-A3B. La liste est ordonnée par index de bloc.

    `octets_experts_par_bloc` isole, dans ce total, les seuls experts routés. La distinction est ce
    qui rend un déport décidable : sur le 35B relevé, un bloc pèse 353 Mo dont 335 Mo d'experts lus
    à 8/256 par token, et 19,5 Mo de dense lus intégralement à chaque token. Sortir le bloc entier de
    la VRAM coûte donc 30 Mo de trafic hôte par token, en sortir les seuls experts en coûte 10,5.
    """

    octets_par_bloc: list[int]
    # Même longueur et même ordre qu'`octets_par_bloc` ; 0 pour un bloc sans tenseur d'experts.
    octets_experts_par_bloc: list[int]
    # Index des blocs portant une projection d'attention, relevés sur les descripteurs. Liste vide :
    # aucun marqueur reconnu, donc aucune mesure — ce n'est pas « ce modèle n'a pas d'attention ».
    blocs_avec_attention: list[int]
    octets_hors_blocs: int = Field(ge=0)
    octets_totaux: int = Field(ge=0)
    blocs_observes: int = Field(ge=0)
    # Un type ggml absent des tables rend le total incomplet : on le dit au lieu de l'arrondir.
    types_ggml_inconnus: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _verifier_alignement(self) -> MesuresTenseurs:
        """Les deux listes par bloc décrivent les mêmes blocs dans le même ordre.

        Un décalage d'un cran ferait attribuer le poids d'experts d'un bloc à son voisin, sans que
        rien ne le signale : l'invariant est vérifié à la construction plutôt que supposé.
        """
        if len(self.octets_experts_par_bloc) != len(self.octets_par_bloc):
            raise ValueError(
                f"octets_experts_par_bloc ({len(self.octets_experts_par_bloc)}) et octets_par_bloc "
                f"({len(self.octets_par_bloc)}) doivent décrire le même nombre de blocs"
            )
        return self

    @property
    def complet(self) -> bool:
        """Vrai si aucun tenseur n'a échappé au calcul de taille."""
        return not self.types_ggml_inconnus

    @property
    def octets_experts_totaux(self) -> int:
        """Poids cumulé des experts routés — 13,057 Gio sur les 14,370 du fichier relevé."""
        return sum(self.octets_experts_par_bloc)

    @property
    def octets_denses_par_bloc(self) -> list[int]:
        """Poids d'un bloc hors experts routés : ce qui est lu intégralement à chaque token."""
        return [
            total - experts
            for total, experts in zip(self.octets_par_bloc, self.octets_experts_par_bloc, strict=True)
        ]


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
    # Reflet exact de `{arch}.feed_forward_length`, rien d'autre. Absente sur `qwen35moe`, qui déclare
    # `expert_feed_forward_length` à la place : le champ vaut alors `None` et le reste. Y recopier la
    # largeur d'un expert serait exactement la substitution silencieuse que la v2 corrige.
    longueur_feed_forward: int | None = None

    nb_experts: int | None = None
    nb_experts_actifs: int | None = None
    experts: ParametresExperts = Field(default_factory=ParametresExperts)

    attention: ParametresAttention = Field(default_factory=ParametresAttention)
    ssm: ParametresSSM = Field(default_factory=ParametresSSM)

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

    @property
    def largeur_ffn_active(self) -> int | None:
        """Largeur FFN réellement vive pour un token — la grandeur qu'un budget doit dimensionner.

        Dense : `longueur_feed_forward`, tel quel. MoE : `expert_used_count` experts routés sont
        évalués simultanément dans le graphe, donc la largeur vive vaut ce nombre multiplié par la
        largeur d'un expert, plus la branche partagée (déjà une largeur totale) évaluée à chaque
        token. Prendre la largeur d'UN expert sous-dimensionnerait d'un facteur 8 sur le modèle relevé.

        `None` dès qu'un terme manque : on ne complète pas une somme de moitié. Une branche partagée
        non déclarée compte pour 0 — c'est ce que dit le fichier, et `coherence` signale le cas où des
        tenseurs `_shexp` existent malgré l'absence de la clé.
        """
        if not self.est_moe:
            return self.longueur_feed_forward
        if self.nb_experts_actifs is None or self.experts.largeur_ffn_expert is None:
            return None
        return self.nb_experts_actifs * self.experts.largeur_ffn_expert + (self.experts.largeur_ffn_partagee or 0)


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


def _booleen(cles: dict[str, ValeurGGUF], cle: str) -> bool | None:
    """Booléen associé à une clé. `None` couvre l'absence *et* le type inattendu — un drapeau non lu
    n'est ni vrai ni faux, et le rendre `False` par défaut inventerait une déclaration.
    """
    valeur = cles.get(cle)
    return valeur if isinstance(valeur, bool) else None


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
        intervalle_attention_pleine=_entier(cles, f"{architecture}.full_attention_interval"),
        sections_rope=_entiers(cles, f"{architecture}.rope.dimension_sections"),
    )


def _experts(cles: dict[str, ValeurGGUF], architecture: str) -> ParametresExperts:
    """Déclaration du mélange d'experts, telle qu'écrite. Toute clé absente reste absente."""
    prefixe = f"{architecture}.expert_"
    return ParametresExperts(
        largeur_ffn_expert=_entier(cles, f"{prefixe}feed_forward_length"),
        largeur_ffn_partagee=_entier(cles, f"{prefixe}shared_feed_forward_length"),
        nb_experts_partages=_entier(cles, f"{prefixe}shared_count"),
        nb_blocs_denses_en_tete=_entier(cles, f"{architecture}.leading_dense_block_count"),
        fonction_routage=_entier(cles, f"{prefixe}gating_func"),
        echelle_poids=_reel(cles, f"{prefixe}weights_scale"),
        poids_normalises=_booleen(cles, f"{prefixe}weights_norm"),
    )


def _ssm(cles: dict[str, ValeurGGUF], architecture: str) -> ParametresSSM:
    """Paramètres de l'état récurrent, tels qu'écrits."""
    prefixe = f"{architecture}.ssm."
    return ParametresSSM(
        dimension_interne=_entier(cles, f"{prefixe}inner_size"),
        dimension_etat=_entier(cles, f"{prefixe}state_size"),
        noyau_convolution=_entier(cles, f"{prefixe}conv_kernel"),
        rang_pas_de_temps=_entier(cles, f"{prefixe}time_step_rank"),
        nb_groupes=_entier(cles, f"{prefixe}group_count"),
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


class _Repartition(BaseModel):
    """Accumulateurs du parcours des descripteurs — détail interne de la mesure."""

    poids_par_bloc: dict[int, int] = Field(default_factory=dict)
    experts_par_bloc: dict[int, int] = Field(default_factory=dict)
    blocs_avec_attention: set[int] = Field(default_factory=set)
    octets_hors_blocs: int = 0
    types_inconnus: set[int] = Field(default_factory=set)


def _repartir(tenseurs: list[InfoTenseur]) -> _Repartition:
    """Classe chaque descripteur : dans un bloc ou non, expert routé ou non, attention ou non.

    Le relevé d'attention se fait avant le calcul de taille : un bloc dont le type ggml serait
    inconnu porte quand même une attention, et l'oublier fausserait le compte des couches à cache KV.
    """
    repartition = _Repartition()
    for tenseur in tenseurs:
        index = _index_bloc(tenseur.nom)
        if index is not None and porte_attention(tenseur.nom):
            repartition.blocs_avec_attention.add(index)
        traits = traits_ggml(tenseur.type_ggml)
        if traits is None:
            repartition.types_inconnus.add(tenseur.type_ggml)
            continue
        octets = traits.octets(tenseur.nb_elements)
        if index is None:
            repartition.octets_hors_blocs += octets
            continue
        repartition.poids_par_bloc[index] = repartition.poids_par_bloc.get(index, 0) + octets
        if est_tenseur_expert(tenseur.nom):
            repartition.experts_par_bloc[index] = repartition.experts_par_bloc.get(index, 0) + octets
    return repartition


def _mesurer_tenseurs(tenseurs: list[InfoTenseur]) -> MesuresTenseurs | None:
    """Somme les octets réellement occupés, bloc par bloc, à partir des types et des formes."""
    if not tenseurs:
        return None

    repartition = _repartir(tenseurs)
    indices = sorted(repartition.poids_par_bloc)
    ordonnes = [repartition.poids_par_bloc[index] for index in indices]
    return MesuresTenseurs(
        octets_par_bloc=ordonnes,
        octets_experts_par_bloc=[repartition.experts_par_bloc.get(index, 0) for index in indices],
        blocs_avec_attention=sorted(repartition.blocs_avec_attention),
        octets_hors_blocs=repartition.octets_hors_blocs,
        octets_totaux=repartition.octets_hors_blocs + sum(ordonnes),
        blocs_observes=len(indices),
        types_ggml_inconnus=sorted(repartition.types_inconnus),
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


def _architecture(entete: EnTeteGGUF) -> str:
    """Nom d'architecture, sans lequel aucune clé préfixée n'est adressable."""
    architecture = _chaine(entete.cles, "general.architecture")
    if not architecture:
        raise MetadonneesIllisibles(
            "`general.architecture` absent de l'en-tête GGUF.",
            remediation="Le fichier est incomplet ou n'est pas un modèle : relancer le téléchargement.",
            details={"chemin": entete.chemin},
        )
    return architecture


def depuis_entete(entete: EnTeteGGUF) -> MetadonneesGGUF:
    """Interprète un en-tête déjà lu. Point d'entrée testable sans fichier ni GPU."""
    architecture = _architecture(entete)
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
        experts=_experts(entete.cles, architecture),
        attention=_attention(entete.cles, architecture),
        ssm=_ssm(entete.cles, architecture),
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
