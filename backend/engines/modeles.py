"""Vocabulaire typé du domaine `engines` : état de santé des moteurs et suivi d'installation.

Aucun champ de ce module n'est rempli par une supposition. Chaque valeur vient soit d'une lecture
du disque, soit d'une sonde exécutée hors process. Un champ non mesuré vaut `None` — jamais une
estimation de repli. C'est exactement l'inverse de la v1, où « installé » et « opérationnel »
étaient deux booléens indépendants qui pouvaient se contredire, et où un venv vide se déclarait
prêt à servir.

Conséquence de conception : `installe` et `fonctionnel` ne sont pas stockés, ils sont dérivés de
`statut`. Deux sources de vérité pour la même information finissent toujours par diverger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field

NomMoteur = Literal["llamacpp", "vllm"]
NiveauEvenement = Literal["info", "avertissement", "erreur", "succes"]

# Architectures CUDA du parc visé (COMPATIBILITE-GPU.md) : sm_86 pour la RTX 3060 de
# développement, sm_120 pour la RTX 5080 cible. Un binaire qui n'expose pas les deux ne couvre
# pas le parc — le domaine `engines` le signale sans prétendre savoir quel GPU est présent :
# c'est le domaine `system` qui mesure le matériel, pas celui-ci.
ARCHITECTURES_PARC: tuple[str, ...] = ("sm_86", "sm_120")


def maintenant_utc() -> datetime:
    """Horodatage des mesures. UTC partout, pour que deux mesures restent comparables."""
    return datetime.now(timezone.utc)


class StatutMoteur(str, Enum):
    """État d'un moteur. Un seul champ porte l'information, les booléens en sont dérivés."""

    ABSENT = "absent"  # rien d'installé
    INCOMPLET = "incomplet"  # présent sur le disque mais jamais validé : installation interrompue
    DEFAILLANT = "defaillant"  # installé, mais la sonde échoue ou révèle un binaire inutilisable
    FONCTIONNEL = "fonctionnel"  # sonde passée : importable et capable de toucher le GPU


class EtapeInstallation(str, Enum):
    """Étapes d'une installation vLLM, dans l'ordre. Sert aussi à calculer la progression."""

    PREPARATION = "preparation"
    CREATION_VENV = "creation_venv"
    MISE_A_JOUR_PIP = "mise_a_jour_pip"
    INSTALLATION_VLLM = "installation_vllm"
    ALIGNEMENT_TRANSFORMERS = "alignement_transformers"
    VALIDATION = "validation"
    FINALISATION = "finalisation"
    # Issues possibles, hors séquence nominale.
    ANNULATION = "annulation"
    ECHEC = "echec"


# Séquence nominale : la progression diffusée est le rapport d'étapes RÉELLEMENT franchies, jamais
# une estimation de durée. Une barre qui avance toute seule pendant un `pip install` de vingt
# minutes ment à l'utilisateur ; ici elle ne bouge que quand quelque chose s'est vraiment terminé.
ETAPES_NOMINALES: tuple[EtapeInstallation, ...] = (
    EtapeInstallation.PREPARATION,
    EtapeInstallation.CREATION_VENV,
    EtapeInstallation.MISE_A_JOUR_PIP,
    EtapeInstallation.INSTALLATION_VLLM,
    EtapeInstallation.ALIGNEMENT_TRANSFORMERS,
    EtapeInstallation.VALIDATION,
    EtapeInstallation.FINALISATION,
)


def progression_de(etape: EtapeInstallation) -> float:
    """Fraction d'étapes franchies une fois `etape` atteinte.

    Une étape hors séquence (annulation, échec) vaut 1.0 : elle ne signale pas un succès mais la
    fin du flux, seul état que l'interface doit retenir pour cesser d'attendre.
    """
    if etape not in ETAPES_NOMINALES:
        return 1.0
    return round((ETAPES_NOMINALES.index(etape) + 1) / len(ETAPES_NOMINALES), 3)


class SanteMoteur(BaseModel):
    """État de santé uniforme d'un moteur, tel qu'exposé hors du domaine."""

    moteur: NomMoteur
    statut: StatutMoteur
    version: str | None = None
    architectures_gpu: tuple[str, ...] = ()
    diagnostic: str = ""
    remediation: str = ""
    # Mesures secondaires (FORCE_CUBLAS, version de torch, chemin du venv…). Texte brut : ce sont
    # des constats destinés à l'affichage et au diagnostic, pas des valeurs de pilotage.
    details: dict[str, str] = Field(default_factory=dict)
    mesure_le: datetime = Field(default_factory=maintenant_utc)

    @computed_field
    @property
    def installe(self) -> bool:
        """Présent sur le disque, quel que soit son état de fonctionnement."""
        return self.statut is not StatutMoteur.ABSENT

    @computed_field
    @property
    def fonctionnel(self) -> bool:
        """Vérifié par une sonde réelle. Ne jamais déduire cette valeur de la seule présence."""
        return self.statut is StatutMoteur.FONCTIONNEL

    @computed_field
    @property
    def couvre_le_parc(self) -> bool:
        """Le binaire embarque-t-il toutes les architectures du parc (sm_86 et sm_120) ?"""
        return all(arch in self.architectures_gpu for arch in ARCHITECTURES_PARC)


class DiagnosticLlamaCpp(BaseModel):
    """Résultat brut de la sonde llama.cpp. Reflet exact de ce que le binaire a rapporté."""

    importable: bool = False
    version: str | None = None
    architectures_gpu: tuple[str, ...] = ()
    force_cublas: bool | None = None
    offload_gpu: bool | None = None
    info_systeme: str = ""
    erreur: str | None = None
    type_erreur: str | None = None


class DiagnosticVllm(BaseModel):
    """Résultat brut de la sonde vLLM, exécutée par le Python du venv concerné."""

    importable: bool = False
    version_vllm: str | None = None
    version_transformers: str | None = None
    version_torch: str | None = None
    version_cuda: str | None = None
    # Point de vigilance documenté : `xgrammar` déclare exiger `transformers<5`, borne trop
    # stricte (COMPATIBILITE-GPU.md). On installe quand même transformers 5 et on VÉRIFIE ici que
    # l'import passe. Tant que ce booléen est vrai, la borne déclarée est bien démentie par la
    # mesure ; s'il devient faux, c'est l'inverse et l'installation est refusée.
    xgrammar_importable: bool | None = None
    architectures_gpu: tuple[str, ...] = ()
    nb_architectures_modeles: int | None = None
    erreur: str | None = None
    type_erreur: str | None = None


class MarqueurInstallation(BaseModel):
    """Fichier d'état déposé dans le venv vLLM — seule preuve qu'une installation est allée au bout.

    Écrit une première fois en `en_cours` au tout début, puis réécrit en `valide` seulement après
    que la sonde a confirmé l'import. Un process tué entre les deux laisse donc un marqueur
    `en_cours` : le venv est alors signalé INCOMPLET, jamais présenté comme utilisable. C'est
    précisément le défaut de la v1 — venv créé, vLLM jamais installé dedans, et un
    `ModuleNotFoundError` sans explication au premier chargement.
    """

    version_demandee: str
    statut: Literal["en_cours", "valide"]
    debute_le: datetime
    validee_le: datetime | None = None
    version_vllm: str | None = None
    version_transformers: str | None = None
    version_torch: str | None = None
    architectures_gpu: tuple[str, ...] = ()
    taille_octets: int | None = None


class VersionVllm(BaseModel):
    """Une installation vLLM parmi les versions cohabitantes."""

    version: str
    chemin: Path
    python: Path
    statut: StatutMoteur
    version_installee: str | None = None
    version_transformers: str | None = None
    version_torch: str | None = None
    architectures_gpu: tuple[str, ...] = ()
    taille_octets: int | None = None
    installee_le: datetime | None = None
    diagnostic: str = ""

    @computed_field
    @property
    def utilisable(self) -> bool:
        """Seul un venv validé peut être proposé au domaine `inference` pour charger un modèle."""
        return self.statut is StatutMoteur.FONCTIONNEL


class EvenementInstallation(BaseModel):
    """Un événement du flux d'installation, diffusable tel quel vers l'interface."""

    version: str
    etape: EtapeInstallation
    message: str
    niveau: NiveauEvenement = "info"
    progression: float = Field(default=0.0, ge=0.0, le=1.0)
    termine: bool = False
    succes: bool | None = None
    horodatage: datetime = Field(default_factory=maintenant_utc)


class EtatMoteurs(BaseModel):
    """Vue d'ensemble du domaine : un état de santé par moteur, plus le détail des venvs vLLM."""

    llamacpp: SanteMoteur
    vllm: SanteMoteur
    versions_vllm: list[VersionVllm] = Field(default_factory=list)
    mesure_le: datetime = Field(default_factory=maintenant_utc)
