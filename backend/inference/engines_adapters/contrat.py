"""Contrat commun des adaptateurs de moteurs : plan accepté, états, options, morceaux générés.

Pourquoi un contrat local plutôt qu'un import direct du planificateur : les adaptateurs doivent
rester testables sans planificateur, sans GPU et sans moteur installé, et la dépendance doit garder
un seul sens — le plan descend vers les moteurs, jamais l'inverse.

`PlanChargement` est la forme *acceptée* par les adaptateurs. `depuis_objet` valide qu'un plan
produit ailleurs la respecte : si un champ manque, l'échec est explicite et nommé, au lieu d'un
attribut lu à `None` qui se transformerait plus loin en « Failed to load model from file ».
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MoteurSupporte(str, Enum):
    """Moteurs pilotés par ce sous-module. Toute autre valeur de plan est un plan invalide."""

    LLAMA_CPP = "llama.cpp"
    VLLM = "vllm"


class CauseEchec(str, Enum):
    """Qualification d'un échec de chargement.

    Existe parce que la v1 remontait « Failed to load model from file » pour tout : le message
    accusait le fichier alors que la cause était ailleurs (VRAM, moteur non compilé, contexte trop
    grand). Une cause nommée est ce qui permet au planificateur de dégrader dans la bonne direction.
    """

    VRAM_INSUFFISANTE = "vram_insuffisante"
    VRAM_NON_LIBEREE = "vram_non_liberee"
    RAM_INSUFFISANTE = "ram_insuffisante"
    CONTEXTE_TROP_GRAND = "contexte_trop_grand"
    ARCHITECTURE_INCONNUE = "architecture_inconnue"
    QUANTIFICATION_INCOMPATIBLE = "quantification_incompatible"
    FICHIER_ILLISIBLE = "fichier_illisible"
    MOTEUR_ABSENT = "moteur_absent"
    MOTEUR_SANS_CUDA = "moteur_sans_cuda"
    PLAN_INCOMPLET = "plan_incomplet"
    DELAI_DEPASSE = "delai_depasse"
    ANNULE = "annule"
    INDETERMINEE = "indeterminee"


class EtatChargement(str, Enum):
    """États observables du superviseur. Un seul est actif à la fois, le GPU étant exclusif."""

    INACTIF = "inactif"
    EN_COURS = "en_cours"
    PRET = "pret"
    ECHOUE = "echoue"


class PlanChargement(BaseModel):
    """Plan produit par le planificateur et appliqué tel quel par un adaptateur.

    Aucun adaptateur ne recalcule une de ces valeurs : le planificateur est seule source de vérité.
    Un champ absent est une erreur de plan, pas une invitation à choisir un défaut.
    """

    # `from_attributes` accepte aussi bien un modèle pydantic du planificateur qu'un dataclass.
    model_config = ConfigDict(from_attributes=True, extra="ignore", frozen=True)

    moteur: MoteurSupporte
    chemin_modele: str
    identifiant_modele: str = ""

    couches_gpu: int = Field(description="Couches déléguées au GPU. -1 = toutes (llama.cpp).")
    contexte: int = Field(gt=0, description="Fenêtre de contexte en tokens.")
    batch: int = Field(gt=0, description="Taille de lot de prompt processing.")
    type_kv_cache: str | None = Field(default=None, description="f16, q8_0, q4_0… None = défaut moteur.")
    flash_attention: bool | None = Field(default=None, description="None = défaut moteur, sinon décision du plan.")

    # Spécifique vLLM : le moteur prélloue la VRAM, la fraction doit venir du plan (jamais du défaut
    # 0.9 de vLLM, intenable sur 16 Go partagés avec le bureau Windows).
    fraction_vram: float | None = Field(default=None, gt=0.0, le=1.0)
    mode_eager: bool = False

    variables_env: dict[str, str] = Field(default_factory=dict)
    # Lignes d'explication produites par le planificateur, transportées telles quelles jusqu'au
    # journal et à l'interface : elles sont affichées, jamais réinterprétées.
    justifications: list[str] = Field(default_factory=list)

    @property
    def nom_affiche(self) -> str:
        """Nom servi aux clients : l'identifiant du plan, à défaut le nom de fichier."""
        if self.identifiant_modele:
            return self.identifiant_modele
        return self.chemin_modele.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]

    @classmethod
    def depuis_objet(cls, objet: Any) -> PlanChargement:
        """Valide un plan venu du planificateur (objet ou dict) contre ce contrat."""
        return cls.model_validate(objet, from_attributes=True)


class MessageChat(BaseModel):
    """Message d'une conversation, au format attendu par les deux moteurs."""

    model_config = ConfigDict(extra="ignore")

    role: Literal["system", "user", "assistant"]
    content: str


class OptionsGeneration(BaseModel):
    """Réglages d'échantillonnage. Ce sont des préférences de génération, pas des mesures machine."""

    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    repetition_penalty: float | None = Field(default=None, gt=0.0)
    max_tokens: int | None = Field(default=None, gt=0)
    stop: list[str] = Field(default_factory=list)
    graine: int | None = None


class MorceauGeneration(BaseModel):
    """Unité du flux de génération. `fin` clôt toujours un flux qui n'a pas levé d'exception."""

    type: Literal["token", "fin", "erreur"]
    contenu: str = ""
    raison_arret: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class EtatMoteur(BaseModel):
    """Retour de `charger` : ce que le moteur sert réellement, et ce que le chargement a coûté."""

    moteur: MoteurSupporte
    modele: str
    pret: bool
    contexte: int
    couches_gpu: int
    port: int | None = None
    duree_chargement_s: float = 0.0
    vram_avant_octets: int | None = None
    vram_apres_octets: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Sante(BaseModel):
    """Sonde d'un moteur : répond-il maintenant, et à quel coût."""

    disponible: bool
    moteur: MoteurSupporte | None = None
    modele: str | None = None
    latence_ms: float | None = None
    detail: str = ""
