"""Entrées du planificateur : métadonnées du modèle, profil machine, préférences utilisateur.

Ces structures sont le contrat d'entrée du planificateur. Toutes leurs valeurs sont **mesurées par
d'autres domaines** (`models` lit l'en-tête GGUF, `system` interroge NVML) puis injectées ici.

Le planificateur ne lit ni le disque, ni le GPU, ni `/proc` : c'est précisément ce qui le rend
testable sans matériel, donc ce qui rend détectables les défauts que la v1 n'a jamais vus.

Aucun champ n'est optionnel « au cas où » : si le domaine `models` ne sait pas lire `block_count`,
il lève `MetadonneesIllisibles` — il ne fournit pas une estimation. La v1 estimait 80 couches là où
le fichier en déclarait 41.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Moteur(str, Enum):
    """Moteur d'inférence. Les deux ne cohabitent jamais sur le GPU (cf. `COMPATIBILITE-GPU.md`)."""

    LLAMA_CPP = "llama.cpp"
    VLLM = "vllm"


class FormatModele(str, Enum):
    """Format des poids sur disque — il détermine quel moteur peut charger le modèle."""

    GGUF = "gguf"
    SAFETENSORS = "safetensors"


class TypeCacheKV(str, Enum):
    """Quantification du cache KV. Ordre de compression croissante : F16 > Q8_0 > Q4_0."""

    F16 = "f16"
    Q8_0 = "q8_0"
    Q4_0 = "q4_0"


class Plateforme(str, Enum):
    """Plateforme d'exécution. WSL2 est distinguée de Linux natif car leurs contraintes diffèrent."""

    LINUX_NATIF = "linux_natif"
    WSL2 = "wsl2"
    WINDOWS = "windows"


class CauseEchec(str, Enum):
    """Cause d'un échec de chargement, telle que rapportée par l'adaptateur de moteur.

    Elle sert uniquement à choisir le palier de dégradation de départ : une saturation VRAM n'appelle
    pas le même levier qu'une saturation RAM hôte.
    """

    MEMOIRE_GPU_INSUFFISANTE = "memoire_gpu_insuffisante"
    MEMOIRE_HOTE_INSUFFISANTE = "memoire_hote_insuffisante"
    CONTEXTE_REFUSE = "contexte_refuse"
    MOTEUR_INDISPONIBLE = "moteur_indisponible"
    INCONNUE = "inconnue"


class MetadonneesModele(BaseModel):
    """Métadonnées **lues** dans le modèle, jamais déduites de son nom de fichier.

    Les clés GGUF correspondantes sont indiquées en commentaire : c'est le contrat que le domaine
    `models` doit honorer.
    """

    model_config = ConfigDict(frozen=True)

    identifiant: str
    format: FormatModele
    architecture: str = ""

    # Taille réelle du (des) fichier(s) de poids sur disque, en octets. Base du calcul du poids
    # par couche : la v1 supposait 150 Mo/couche là où la mesure donne 436 Mo.
    taille_octets: int = Field(gt=0)

    # `{arch}.block_count` — nombre RÉEL de couches transformer.
    nombre_couches: int = Field(gt=0)

    # `{arch}.embedding_length`
    dimension_embedding: int = Field(gt=0)

    # `{arch}.feed_forward_length` — dimension interne du bloc FFN, dimensionne les tampons.
    dimension_ffn: int = Field(gt=0)

    # `{arch}.attention.head_count` et `.head_count_kv` (GQA : moins de têtes KV que de têtes Q).
    nombre_tetes_attention: int = Field(gt=0)
    nombre_tetes_kv: int = Field(gt=0)

    # `{arch}.attention.key_length` / `.value_length`. Absentes sur certaines architectures, où la
    # convention est `dimension_embedding / nombre_tetes_attention` — mais Qwen3 déclare un
    # `head_dim` qui NE suit PAS cette convention. Lire d'abord, dériver seulement en dernier
    # recours (cf. `budget.dimension_tete`).
    dimension_tete: int | None = Field(default=None, gt=0)

    # `{arch}.context_length` — plafond d'entraînement. Au-delà, le modèle divague.
    contexte_entrainement_max: int = Field(gt=0)

    # Longueur de `tokenizer.ggml.tokens` : dimensionne le tampon de logits.
    taille_vocabulaire: int = Field(gt=0)

    quantification: str | None = None
    est_moe: bool = False

    @model_validator(mode="after")
    def _verifier_coherence(self) -> MetadonneesModele:
        """Une métadonnée incohérente doit échouer ici, pas produire un plan silencieusement faux."""
        if self.nombre_tetes_kv > self.nombre_tetes_attention:
            raise ValueError(
                f"nombre_tetes_kv ({self.nombre_tetes_kv}) > nombre_tetes_attention "
                f"({self.nombre_tetes_attention}) : métadonnées contradictoires."
            )
        return self


class ModeleCharge(BaseModel):
    """Modèle déjà résident sur le GPU, avec la VRAM qu'il occupe réellement.

    vLLM prééalloue sa VRAM et ne la rend qu'à l'arrêt du processus : sur 16 Go, aucune
    cohabitation n'est possible. Le planificateur traite donc le GPU comme une ressource exclusive
    et exige l'éjection de tout ce qui est listé ici.
    """

    model_config = ConfigDict(frozen=True)

    identifiant: str
    moteur: Moteur
    vram_octets: int = Field(ge=0)


class ProfilMachine(BaseModel):
    """État matériel mesuré au moment du chargement — pas au démarrage du backend.

    `vram_libre_octets` est la VRAM réellement libre : elle inclut déjà ce que consomme le bureau
    (~1,2 Go sur la machine cible). Ne rien re-soustraire à ce titre, ce serait un double comptage.
    """

    model_config = ConfigDict(frozen=True)

    plateforme: Plateforme
    index_gpu: int = Field(default=0, ge=0)
    nom_gpu: str = ""
    vram_totale_octets: int = Field(gt=0)
    vram_libre_octets: int = Field(ge=0)
    ram_libre_octets: int = Field(ge=0)
    moteurs_disponibles: tuple[Moteur, ...] = (Moteur.LLAMA_CPP,)
    modeles_charges: tuple[ModeleCharge, ...] = ()

    # Capacité de calcul CUDA, ex. (8, 6) pour Ampere, (12, 0) pour Blackwell.
    capacite_calcul: tuple[int, int] | None = None

    @model_validator(mode="after")
    def _verifier_vram(self) -> ProfilMachine:
        if self.vram_libre_octets > self.vram_totale_octets:
            raise ValueError("vram_libre_octets dépasse vram_totale_octets : mesure incohérente.")
        return self


class PreferencesUtilisateur(BaseModel):
    """Ce que l'utilisateur demande. Rien n'est garanti : tout est plafonné par la machine.

    Une préférence **plus conservatrice** que ce que la machine permet est respectée telle quelle —
    l'utilisateur a le droit de vouloir moins. Une préférence plus ambitieuse est ramenée au maximum
    tenable, et le plan explique le plafonnement.
    """

    model_config = ConfigDict(frozen=True)

    contexte: int | None = Field(default=None, gt=0)
    batch: int | None = Field(default=None, gt=0)
    couches_gpu: int | None = Field(default=None, ge=0)
    type_cache_kv: TypeCacheKV = TypeCacheKV.F16
    moteur: Moteur | None = None
    flash_attention: bool = True

    # Mémoire unifiée CUDA : utile sur Linux natif pour laisser déborder les poids, NUISIBLE sous
    # WSL2 (mesure : 20 Go de RAM occupés, VRAM figée à 2 Go). La préférence existe, la plateforme
    # tranche — cf. `environnement.py`.
    autoriser_memoire_unifiee: bool = False

    # Réserve pour la fragmentation de l'allocateur CUDA, en fraction du total alloué.
    # Valeur par défaut PRUDENTE ET NON MESURÉE sur la machine cible : c'est le seul paramètre du
    # budget qui ne se dérive pas d'une grandeur du modèle. Elle est exposée ici, justifiée dans le
    # plan, et devra être resserrée dès qu'une mesure existera.
    ratio_fragmentation: float = Field(default=0.05, ge=0.0, le=0.5)


class DemandeDeChargement(BaseModel):
    """Les trois entrées réunies : c'est l'unique argument de `planifier`."""

    model_config = ConfigDict(frozen=True)

    metadonnees: MetadonneesModele
    profil: ProfilMachine
    preferences: PreferencesUtilisateur = PreferencesUtilisateur()
