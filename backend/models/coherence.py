"""Détection des incohérences d'un modèle — ce qu'il déclare confronté à ce qu'il contient.

Un modèle peut être syntaxiquement lisible et pourtant inchargeable. Les deux cas mesurés sur la
v1 :

- un AWQ déclarait dans `config.json` une tour de vision (`vision_config`) dont **aucun poids**
  n'existait dans les safetensors ; le chargement échouait avec un message pointant un fichier, ce
  qui envoyait chercher au mauvais endroit pendant des heures ;
- le même déclarait un `intermediate_size` non divisible par le `group_size` de sa quantification,
  ce qui rend le déquantifieur incapable de reconstituer les tuiles.

Ce module dit **explicitement** ce qui cloche, avec le chiffre qui le prouve. Il ne répare rien et
ne devine rien : il compare deux lectures et signale l'écart.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field

from backend.core.errors import MetadonneesIllisibles
from backend.models.gguf_metadata import MetadonneesGGUF, depuis_entete, indices_de_blocs
from backend.models.gguf_reader import EnTeteGGUF, lire_entete
from backend.models.gguf_types import MARQUEUR_EXPERT_PARTAGE, est_tenseur_expert
from backend.models.safetensors_reader import IndexSafetensors, lire_config, lire_index
from backend.models.storage import FormatModele, detecter_format, fichiers_gguf

# Préfixes sous lesquels les poids d'une tour de vision sont écrits, toutes familles confondues.
MARQUEURS_VISION = (
    "vision_model.",
    "vision_tower.",
    "visual.",
    "multi_modal_projector.",
    "mm_projector.",
    "image_newline",
)

# Tenseurs propres aux quantifications par blocs (AWQ, GPTQ) : sans eux, la déquantification est
# impossible quelle que soit la configuration déclarée.
MARQUEURS_QUANTIFIES = ("qweight", "qzeros", "scales")

MOTIF_COUCHE = re.compile(r"\.layers\.(\d+)\.")


class NiveauIncoherence(str, Enum):
    """Gravité d'un écart. `BLOQUANT` signifie : le chargement échouera, inutile d'essayer."""

    AVERTISSEMENT = "avertissement"
    BLOQUANT = "bloquant"


class Incoherence(BaseModel):
    """Un écart précis entre ce qui est déclaré et ce qui est présent."""

    code: str
    niveau: NiveauIncoherence
    message: str
    remediation: str = ""
    details: dict[str, object] = Field(default_factory=dict)


class RapportCoherence(BaseModel):
    """Résultat d'une vérification. `chargeable` est ce qu'une interface doit regarder."""

    chemin: str
    format: FormatModele | None
    incoherences: list[Incoherence] = Field(default_factory=list)

    @property
    def chargeable(self) -> bool:
        """Faux dès qu'une incohérence bloquante a été relevée."""
        return not any(item.niveau is NiveauIncoherence.BLOQUANT for item in self.incoherences)

    @property
    def bloquantes(self) -> list[Incoherence]:
        return [item for item in self.incoherences if item.niveau is NiveauIncoherence.BLOQUANT]


def _incoherence(
    code: str,
    niveau: NiveauIncoherence,
    message: str,
    remediation: str = "",
    **details: object,
) -> Incoherence:
    return Incoherence(code=code, niveau=niveau, message=message, remediation=remediation, details=details)


# --- GGUF ------------------------------------------------------------------------------------


def _verifier_blocs_gguf(metadonnees: MetadonneesGGUF, entete: EnTeteGGUF) -> list[Incoherence]:
    """Le nombre de blocs déclaré doit correspondre aux blocs réellement décrits."""
    mesures = metadonnees.mesures
    if mesures is None or not entete.tenseurs:
        return []

    ecarts: list[Incoherence] = []
    if mesures.blocs_observes != metadonnees.block_count:
        ecarts.append(
            _incoherence(
                "block_count_incoherent",
                NiveauIncoherence.BLOQUANT,
                f"{metadonnees.block_count} blocs déclarés, {mesures.blocs_observes} décrits par les tenseurs.",
                "Fichier incomplet ou fusion de shards manquante : relancer le téléchargement.",
                block_count_declare=metadonnees.block_count,
                blocs_observes=mesures.blocs_observes,
            )
        )
    indices = indices_de_blocs(entete.tenseurs)
    if indices and max(indices) + 1 != len(indices):
        manquants = sorted(set(range(max(indices) + 1)) - indices)
        ecarts.append(
            _incoherence(
                "blocs_non_contigus",
                NiveauIncoherence.BLOQUANT,
                f"Les index de blocs ne forment pas une suite continue : {len(manquants)} manquant(s).",
                "Le fichier a probablement été tronqué ou concaténé de travers : retélécharger.",
                blocs_manquants=manquants[:20],
            )
        )
    return ecarts


def _verifier_experts_gguf(metadonnees: MetadonneesGGUF, entete: EnTeteGGUF) -> list[Incoherence]:
    """Un modèle qui déclare des experts doit porter les tenseurs correspondants."""
    nb_experts = metadonnees.nb_experts
    if not nb_experts or nb_experts <= 1 or not entete.tenseurs:
        return []

    tenseurs_experts = [tenseur for tenseur in entete.tenseurs if est_tenseur_expert(tenseur.nom)]
    if not tenseurs_experts:
        return [
            _incoherence(
                "experts_declares_sans_poids",
                NiveauIncoherence.BLOQUANT,
                f"{nb_experts} experts déclarés, aucun tenseur d'experts présent.",
                "Le fichier ne contient pas le modèle annoncé : retélécharger la bonne variante.",
                nb_experts_declares=nb_experts,
            )
        ]

    # La dernière dimension d'un tenseur d'experts porte leur cardinal : c'est la vérification qui
    # attrape un fichier construit pour un autre nombre d'experts que celui annoncé.
    dimensions = {tenseur.dimensions[-1] for tenseur in tenseurs_experts if tenseur.dimensions}
    if dimensions and nb_experts not in dimensions:
        return [
            _incoherence(
                "cardinal_experts_incoherent",
                NiveauIncoherence.BLOQUANT,
                f"{nb_experts} experts déclarés, dimensions observées sur les tenseurs : {sorted(dimensions)}.",
                "Métadonnées et poids proviennent de deux exports différents : retélécharger.",
                nb_experts_declares=nb_experts,
                dimensions_observees=sorted(dimensions),
            )
        ]
    return []


def _verifier_largeur_ffn_moe(metadonnees: MetadonneesGGUF) -> list[Incoherence]:
    """Un MoE doit déclarer de quoi dimensionner la FFN vive d'un token, sinon rien n'est budgétable.

    Le cas mesuré : `qwen35moe` ne déclare pas `feed_forward_length` mais
    `expert_feed_forward_length`. Tant que la seconde n'était pas lue, la cible de chargement ne se
    construisait pas et le modèle n'était pas planifiable — sans que rien ne dise laquelle manquait.
    """
    if not metadonnees.est_moe or metadonnees.largeur_ffn_active is not None:
        return []
    return [
        _incoherence(
            "largeur_ffn_indeterminee",
            NiveauIncoherence.AVERTISSEMENT,
            f"Modèle à {metadonnees.nb_experts} experts : ni `{metadonnees.architecture}."
            "feed_forward_length` ni le couple (`expert_feed_forward_length`, `expert_used_count`) "
            "ne sont lisibles, la largeur FFN vive d'un token est inconnue.",
            "Ne pas y substituer la largeur d'un expert : elle sous-dimensionne du nombre d'experts "
            "actifs. Le plan doit traiter cette largeur comme non mesurée.",
            largeur_ffn_expert=metadonnees.experts.largeur_ffn_expert,
            nb_experts_actifs=metadonnees.nb_experts_actifs,
        )
    ]


def _verifier_expert_partage(metadonnees: MetadonneesGGUF, entete: EnTeteGGUF) -> list[Incoherence]:
    """Des tenseurs `_shexp` présents sans la largeur correspondante font une somme incomplète."""
    partages = [tenseur for tenseur in entete.tenseurs if MARQUEUR_EXPERT_PARTAGE in tenseur.nom]
    if not partages or metadonnees.experts.largeur_ffn_partagee is not None:
        return []
    return [
        _incoherence(
            "expert_partage_sans_largeur",
            NiveauIncoherence.AVERTISSEMENT,
            f"{len(partages)} tenseur(s) `{MARQUEUR_EXPERT_PARTAGE}` présents, "
            f"`{metadonnees.architecture}.expert_shared_feed_forward_length` absente.",
            "La branche partagée est évaluée à chaque token : sa largeur manque à la somme, où elle "
            "compte pour 0, et `largeur_ffn_active` est sous-estimée d'autant.",
            nb_tenseurs_partages=len(partages),
        )
    ]


def _verifier_attention_hybride(metadonnees: MetadonneesGGUF) -> list[Incoherence]:
    """`full_attention_interval` déclaré, confronté aux blocs qui portent réellement une attention.

    C'est la mesure la plus lourde du fichier : sur les deux modèles de la machine, une couche sur
    quatre seulement porte un cache KV. Facturer le KV sur toutes en invente 3,3 Gio à 57k.
    """
    intervalle = metadonnees.attention.intervalle_attention_pleine
    mesures = metadonnees.mesures
    if intervalle is None or intervalle <= 0 or mesures is None or not mesures.blocs_avec_attention:
        return []

    # Comparaison de CARDINAUX seulement : la convention d'indexation des couches d'attention n'est
    # pas documentée par le format, et on ne la suppose pas pour signaler un écart.
    attendus = metadonnees.block_count // intervalle
    observes = len(mesures.blocs_avec_attention)
    if attendus == observes:
        return []
    return [
        _incoherence(
            "intervalle_attention_incoherent",
            NiveauIncoherence.AVERTISSEMENT,
            f"`full_attention_interval` vaut {intervalle} sur {metadonnees.block_count} blocs, soit "
            f"{attendus} couche(s) d'attention attendue(s) ; {observes} en portent effectivement.",
            "Dimensionner le cache KV sur les blocs observés, jamais sur la clé seule : l'écart se "
            "paie en VRAM inventée ou en dépassement.",
            intervalle=intervalle,
            couches_attendues=attendus,
            couches_observees=observes,
        )
    ]


def _verifier_taille_gguf(metadonnees: MetadonneesGGUF, entete: EnTeteGGUF) -> list[Incoherence]:
    """Les poids calculés doivent tenir dans le fichier réellement présent sur le disque."""
    mesures = metadonnees.mesures
    if mesures is None or not mesures.complet:
        return []

    requis = entete.offset_donnees + mesures.octets_totaux
    if requis > entete.taille_fichier_octets:
        manquant = requis - entete.taille_fichier_octets
        return [
            _incoherence(
                "fichier_tronque",
                NiveauIncoherence.BLOQUANT,
                f"Les descripteurs décrivent {requis} octets, le fichier n'en compte que "
                f"{entete.taille_fichier_octets} ({manquant} manquants).",
                "Téléchargement interrompu : relancer, la reprise repart des octets déjà écrits.",
                octets_requis=requis,
                octets_presents=entete.taille_fichier_octets,
            )
        ]
    return []


def _verifier_signaux_gguf(metadonnees: MetadonneesGGUF, entete: EnTeteGGUF) -> list[Incoherence]:
    """Écarts non bloquants, mais qui doivent être visibles avant de planifier un chargement."""
    signaux: list[Incoherence] = []
    mesures = metadonnees.mesures

    if mesures is not None and mesures.types_ggml_inconnus:
        signaux.append(
            _incoherence(
                "types_ggml_inconnus",
                NiveauIncoherence.AVERTISSEMENT,
                f"Types de tenseurs non répertoriés : {mesures.types_ggml_inconnus}. Le poids total est partiel.",
                "Mettre à jour EchoHub, ou considérer la taille du fichier plutôt que le total des tenseurs.",
                types=mesures.types_ggml_inconnus,
            )
        )
    if metadonnees.contexte_natif is None:
        signaux.append(
            _incoherence(
                "contexte_natif_absent",
                NiveauIncoherence.AVERTISSEMENT,
                f"`{metadonnees.architecture}.context_length` absent : le contexte natif est inconnu.",
                "Le plan de chargement devra s'en tenir à une valeur explicitement choisie.",
            )
        )
    if entete.nb_tenseurs_declares != len(entete.tenseurs) and entete.tenseurs:
        signaux.append(
            _incoherence(
                "nombre_tenseurs_incoherent",
                NiveauIncoherence.AVERTISSEMENT,
                f"{entete.nb_tenseurs_declares} tenseurs annoncés, {len(entete.tenseurs)} descripteurs lus.",
                "",
            )
        )
    return signaux


def verifier_gguf(chemin: Path) -> RapportCoherence:
    """Vérifie un fichier GGUF en confrontant ses métadonnées à ses descripteurs de tenseurs."""
    entete = lire_entete(chemin)
    metadonnees = depuis_entete(entete)
    incoherences = [
        *_verifier_blocs_gguf(metadonnees, entete),
        *_verifier_experts_gguf(metadonnees, entete),
        *_verifier_largeur_ffn_moe(metadonnees),
        *_verifier_expert_partage(metadonnees, entete),
        *_verifier_attention_hybride(metadonnees),
        *_verifier_taille_gguf(metadonnees, entete),
        *_verifier_signaux_gguf(metadonnees, entete),
    ]
    return RapportCoherence(chemin=str(chemin), format=FormatModele.GGUF, incoherences=incoherences)


# --- safetensors -----------------------------------------------------------------------------


def _verifier_vision(config: dict[str, object], index: IndexSafetensors) -> list[Incoherence]:
    """Le cas mesuré : une tour de vision déclarée dont aucun poids n'existe."""
    declare_vision = any(cle in config for cle in ("vision_config", "vision_tower_config", "vision_tower"))
    if not declare_vision:
        return []

    presents = [nom for nom in index.tenseurs if any(marqueur in nom for marqueur in MARQUEURS_VISION)]
    if presents:
        return []
    return [
        _incoherence(
            "vision_declaree_sans_poids",
            NiveauIncoherence.BLOQUANT,
            "`config.json` déclare une tour de vision, aucun poids de vision n'est présent dans les safetensors.",
            "Utiliser la variante texte seul de ce modèle, ou un dépôt dont les poids de vision existent. "
            "L'erreur de chargement qui en découle pointe un fichier de code et induit en erreur.",
            marqueurs_recherches=list(MARQUEURS_VISION),
            nb_tenseurs=len(index.tenseurs),
        )
    ]


def _verifier_couches(config: dict[str, object], index: IndexSafetensors) -> list[Incoherence]:
    """`num_hidden_layers` confronté au plus grand index de couche réellement présent."""
    declare = config.get("num_hidden_layers")
    if not isinstance(declare, int) or isinstance(declare, bool) or not index.tenseurs:
        return []

    indices = {int(trouve.group(1)) for nom in index.tenseurs if (trouve := MOTIF_COUCHE.search(nom))}
    if not indices:
        return []
    observees = max(indices) + 1
    if observees == declare:
        return []
    return [
        _incoherence(
            "nombre_de_couches_incoherent",
            NiveauIncoherence.BLOQUANT,
            f"`num_hidden_layers` vaut {declare}, les poids n'en décrivent que {observees}.",
            "Téléchargement incomplet ou dépôt incohérent : retélécharger avant de planifier un chargement.",
            couches_declarees=declare,
            couches_observees=observees,
        )
    ]


def _verifier_quantification(config: dict[str, object], index: IndexSafetensors) -> list[Incoherence]:
    """Cohérence de la configuration de quantification avec les poids et les dimensions."""
    quantification = config.get("quantization_config")
    if not isinstance(quantification, dict):
        return []

    ecarts: list[Incoherence] = []
    methode = quantification.get("quant_method")
    if isinstance(methode, str) and methode.lower() in ("awq", "gptq"):
        quantifies = any(marqueur in nom for nom in index.tenseurs for marqueur in MARQUEURS_QUANTIFIES)
        if index.tenseurs and not quantifies:
            ecarts.append(
                _incoherence(
                    "quantification_declaree_sans_poids",
                    NiveauIncoherence.BLOQUANT,
                    f"Quantification `{methode}` déclarée, aucun tenseur `qweight`/`scales` présent.",
                    "Le dépôt mélange une config quantifiée et des poids pleine précision : choisir l'un des deux.",
                    methode=methode,
                )
            )
    ecarts.extend(_verifier_group_size(config, quantification))
    return ecarts


def _verifier_group_size(config: dict[str, object], quantification: dict[str, object]) -> list[Incoherence]:
    """Les dimensions quantifiées doivent être divisibles par le `group_size`.

    C'est la seconde moitié du cas mesuré : `intermediate_size: 4304` avec un `group_size: 128`.
    """
    group_size = quantification.get("group_size")
    if not isinstance(group_size, int) or isinstance(group_size, bool) or group_size <= 0:
        return []

    ecarts: list[Incoherence] = []
    for nom_dimension in ("hidden_size", "intermediate_size"):
        valeur = config.get(nom_dimension)
        if not isinstance(valeur, int) or isinstance(valeur, bool):
            continue
        if valeur % group_size:
            ecarts.append(
                _incoherence(
                    "dimension_non_divisible",
                    NiveauIncoherence.BLOQUANT,
                    f"`{nom_dimension}` vaut {valeur}, non divisible par le `group_size` {group_size}.",
                    "Les tuiles de déquantification ne tombent pas juste : ce dépôt n'est pas chargeable tel quel.",
                    dimension=nom_dimension,
                    valeur=valeur,
                    group_size=group_size,
                )
            )
    return ecarts


def _verifier_fichiers(index: IndexSafetensors) -> list[Incoherence]:
    """Tout ce que l'index de sharding promet doit exister sur le disque."""
    ecarts: list[Incoherence] = []
    if index.fichiers_manquants:
        ecarts.append(
            _incoherence(
                "shards_manquants",
                NiveauIncoherence.BLOQUANT,
                f"{len(index.fichiers_manquants)} fichier(s) de poids référencés par l'index sont absents.",
                "Téléchargement incomplet : relancer, la reprise ne retéléchargera que ce qui manque.",
                fichiers=index.fichiers_manquants[:20],
            )
        )
    if index.tenseurs_manquants:
        ecarts.append(
            _incoherence(
                "tenseurs_manquants",
                NiveauIncoherence.BLOQUANT,
                f"{len(index.tenseurs_manquants)} tenseur(s) annoncés par l'index sont absents des poids lus.",
                "Le dépôt est incohérent : retélécharger.",
                tenseurs=index.tenseurs_manquants[:20],
            )
        )
    return ecarts


def verifier_safetensors(dossier: Path) -> RapportCoherence:
    """Vérifie un modèle safetensors en croisant `config.json` et l'index réel des tenseurs."""
    index = lire_index(dossier)
    config = lire_config(dossier)
    if config is None:
        incoherence = _incoherence(
            "config_absente",
            NiveauIncoherence.BLOQUANT,
            "`config.json` absent ou illisible : impossible de vérifier ce que le modèle déclare.",
            "Relancer le téléchargement du dépôt complet.",
        )
        return RapportCoherence(
            chemin=str(dossier),
            format=FormatModele.SAFETENSORS,
            incoherences=[incoherence, *_verifier_fichiers(index)],
        )

    incoherences = [
        *_verifier_fichiers(index),
        *_verifier_vision(config, index),
        *_verifier_couches(config, index),
        *_verifier_quantification(config, index),
    ]
    return RapportCoherence(chemin=str(dossier), format=FormatModele.SAFETENSORS, incoherences=incoherences)


def verifier_modele(chemin: Path) -> RapportCoherence:
    """Vérifie un modèle, fichier GGUF ou dossier safetensors, en choisissant le contrôle adapté."""
    if chemin.is_file() and chemin.suffix.lower() == ".gguf":
        return verifier_gguf(chemin)

    if not chemin.is_dir():
        raise MetadonneesIllisibles(
            f"Chemin de modèle inexploitable : {chemin}",
            remediation="Indiquer un fichier .gguf ou un dossier de modèle téléchargé.",
            details={"chemin": str(chemin)},
        )

    format_detecte = detecter_format(chemin)
    if format_detecte is FormatModele.GGUF:
        return verifier_gguf(fichiers_gguf(chemin)[0])
    if format_detecte is FormatModele.SAFETENSORS:
        return verifier_safetensors(chemin)

    logger.warning("Aucun poids reconnu dans {}", chemin)
    incoherence = _incoherence(
        "aucun_poids",
        NiveauIncoherence.BLOQUANT,
        "Le dossier ne contient ni fichier GGUF ni safetensors.",
        "Le téléchargement n'a probablement jamais abouti : le relancer.",
    )
    return RapportCoherence(chemin=str(chemin), format=None, incoherences=[incoherence])
