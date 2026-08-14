"""Structures typées du domaine `system` — ce que la machine EST, mesuré à l'instant t.

Ces modèles sont le contrat que le planificateur consomme. Deux principes hérités des défauts
mesurés sur la v1 :

1. **une absence se représente, elle ne se remplace pas.** Pas de GPU, pas de pilote lisible, pas
   de RAM mesurable : le champ vaut `None` ou une liste vide, jamais une valeur inventée. La v1
   estimait quand elle ne savait pas (80 couches devinées pour 41 réelles) ;
2. **les valeurs dérivées sont calculées ici, une seule fois.** `gpu_principal`, `vram_libre_octets`
   et les contraintes de plateforme sont sérialisés avec le profil : le frontend les affiche, il ne
   les recalcule pas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, computed_field

# Seuil de pilote pour les RTX 50xx (Blackwell) — relevé dans COMPATIBILITE-GPU.md, pas déduit.
VERSION_PILOTE_MIN_BLACKWELL = 570

# `sm_120` et au-delà : compute capability majeure à partir de laquelle on est sur Blackwell.
COMPUTE_MAJEUR_BLACKWELL = 12


class Plateforme(str, Enum):
    """Plateforme d'exécution. La distinction WSL2 / Linux natif porte des contraintes opposées."""

    WSL2 = "wsl2"
    LINUX_NATIF = "linux_natif"
    WINDOWS = "windows"
    MACOS = "macos"
    INCONNUE = "inconnue"


class SourceMesureGpu(str, Enum):
    """Instrument ayant produit le relevé. Affiché à l'utilisateur : une mesure a une provenance."""

    NVML = "nvml"
    NVIDIA_SMI = "nvidia_smi"
    AUCUNE = "aucune"


class SyntaxeGpuDocker(str, Enum):
    """Syntaxe d'exposition du GPU à Docker. Elle est INVERSÉE entre WSL2 et Linux natif."""

    RESERVATIONS = "deploy_reservations"
    CDI = "cdi"


class Gpu(BaseModel):
    """Un GPU NVIDIA et son état mémoire à l'instant de la mesure."""

    index: int = Field(ge=0)
    nom: str
    compute_majeur: int | None = None
    compute_mineur: int | None = None
    vram_totale_octets: int = Field(ge=0)
    vram_libre_octets: int = Field(ge=0)
    vram_utilisee_octets: int = Field(ge=0)
    utilisation_pct: int | None = None
    temperature_c: int | None = None

    @computed_field
    @property
    def architecture_sm(self) -> str | None:
        """Nom d'architecture CUDA (`sm_86`, `sm_120`) — celui qu'attend `CMAKE_CUDA_ARCHITECTURES`."""
        if self.compute_majeur is None or self.compute_mineur is None:
            return None
        return f"sm_{self.compute_majeur}{self.compute_mineur}"

    @computed_field
    @property
    def est_blackwell(self) -> bool:
        """Blackwell impose un plancher de pilote ; le savoir conditionne l'avertissement associé."""
        return self.compute_majeur is not None and self.compute_majeur >= COMPUTE_MAJEUR_BLACKWELL


class PiloteNvidia(BaseModel):
    """Version du pilote NVIDIA de l'hôte.

    Sous WSL2 c'est le pilote **Windows** qui est rapporté : installer un pilote Linux dans la
    distro casse le passthrough, la version vue ici reste donc celle de l'hôte.
    """

    version: str

    @computed_field
    @property
    def version_majeure(self) -> int | None:
        """Composante majeure (`581.29` -> `581`), seule comparable au seuil Blackwell."""
        tete = self.version.strip().split(".", maxsplit=1)[0]
        return int(tete) if tete.isdigit() else None

    @computed_field
    @property
    def supporte_blackwell(self) -> bool:
        """`False` aussi quand la version est illisible : on ne présume pas d'un pilote inconnu."""
        majeure = self.version_majeure
        return majeure is not None and majeure >= VERSION_PILOTE_MIN_BLACKWELL


class ReleveGpu(BaseModel):
    """Résultat d'une lecture GPU par une source donnée. `gpus` vide = machine sans GPU NVIDIA."""

    source: SourceMesureGpu
    pilote: PiloteNvidia | None = None
    gpus: list[Gpu] = Field(default_factory=list)


class Memoire(BaseModel):
    """Mémoire système. `disponible` (et non `libre`) : c'est ce qu'un process peut réellement prendre."""

    totale_octets: int = Field(ge=0)
    disponible_octets: int = Field(ge=0)

    @computed_field
    @property
    def utilisee_octets(self) -> int:
        return max(0, self.totale_octets - self.disponible_octets)

    @computed_field
    @property
    def pourcentage_utilise(self) -> float:
        if self.totale_octets <= 0:
            return 0.0
        return round(100.0 * self.utilisee_octets / self.totale_octets, 1)


class ContraintesPlateforme(BaseModel):
    """Ce que la plateforme INTERDIT ou IMPOSE, pas seulement son nom.

    Le planificateur lit ces champs sans avoir à connaître la table des pièges par plateforme :
    nommer « WSL2 » ne sert à rien s'il faut ensuite redécouvrir ailleurs ce que WSL2 implique.
    """

    plateforme: Plateforme
    memoire_unifiee_cuda: bool
    variables_env_imposees: dict[str, str] = Field(default_factory=dict)
    ram_plafonnee_par_hote: bool
    pin_memory_disponible: bool
    syntaxe_gpu_docker: SyntaxeGpuDocker
    justifications: dict[str, str] = Field(default_factory=dict)


class ProfilMachine(BaseModel):
    """Agrégat matériel complet — l'entrée du planificateur.

    Instantané daté : un profil relu plus tard décrit la machine telle qu'elle était, pas telle
    qu'elle est. Toujours en redemander un avant de décider d'un chargement.
    """

    mesure_le: datetime
    plateforme: Plateforme
    version_noyau: str
    contraintes: ContraintesPlateforme
    source_gpu: SourceMesureGpu
    pilote: PiloteNvidia | None = None
    gpus: list[Gpu] = Field(default_factory=list)
    memoire: Memoire | None = None
    avertissements: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def a_gpu(self) -> bool:
        return bool(self.gpus)

    @computed_field
    @property
    def gpu_principal(self) -> Gpu | None:
        """GPU visé par le planificateur : le mieux doté en VRAM.

        Un seul compte, parce que le GPU est une ressource exclusive — vLLM préalloue la VRAM et
        ne la rend qu'à l'arrêt, aucune cohabitation n'est possible sur 16 Go.
        """
        return max(self.gpus, key=lambda gpu: gpu.vram_totale_octets, default=None)

    @computed_field
    @property
    def vram_libre_octets(self) -> int:
        """Budget VRAM du moment. `0` sans GPU : le planificateur doit viser une exécution CPU."""
        principal = self.gpu_principal
        return principal.vram_libre_octets if principal is not None else 0

    @computed_field
    @property
    def vram_totale_octets(self) -> int:
        principal = self.gpu_principal
        return principal.vram_totale_octets if principal is not None else 0

    @computed_field
    @property
    def memoire_mesuree(self) -> bool:
        """`False` = RAM inconnue. Distingue « rien de libre » de « on n'a pas pu mesurer »."""
        return self.memoire is not None

    @computed_field
    @property
    def ram_disponible_octets(self) -> int:
        """`0` quand la mesure a échoué : aucun offload CPU ne doit être planifié à l'aveugle."""
        return self.memoire.disponible_octets if self.memoire is not None else 0
