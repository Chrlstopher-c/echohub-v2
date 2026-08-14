"""Domaine `system` — sur quelle machine tourne-t-on, et de quoi dispose-t-on maintenant ?

Seule source de vérité matérielle du planificateur : plateforme et contraintes associées, GPU,
VRAM libre à l'instant t, RAM disponible, version du pilote NVIDIA.

Trois règles tenues par ce domaine :

- **on mesure, on ne suppose pas.** Aucune valeur n'est déduite d'un nom de modèle ou d'une
  convention. Ce qui n'a pas pu être lu vaut `None` ou liste vide ;
- **aucun cache.** `profil_machine()` remesure à chaque appel — la VRAM libre change entre deux
  chargements, et c'est précisément la valeur sur laquelle le planificateur décide ;
- **on dégrade, on n'explose pas.** Sans GPU, sans pilote, sans NVML, le profil est produit quand
  même, assorti d'avertissements affichables.

Interface publique — les autres domaines n'importent rien d'autre que ceci :

    from backend.system import profil_machine

    profil = profil_machine()
    budget_vram = profil.vram_libre_octets
    if not profil.contraintes.memoire_unifiee_cuda:
        ...  # sous WSL2 : jamais de débordement VRAM -> RAM, la mesure l'a tranché
"""

from backend.system.api import routeur as routeur_system
from backend.system.gpu import relever_gpu
from backend.system.memoire import relever_memoire
from backend.system.modeles import (
    COMPUTE_MAJEUR_BLACKWELL,
    VERSION_PILOTE_MIN_BLACKWELL,
    ContraintesPlateforme,
    Gpu,
    Memoire,
    PiloteNvidia,
    Plateforme,
    ProfilMachine,
    ReleveGpu,
    SourceMesureGpu,
    SyntaxeGpuDocker,
)
from backend.system.plateforme import contraintes_plateforme, detecter_plateforme
from backend.system.profil import profil_machine

__all__ = [
    # Mesure
    "profil_machine",
    "relever_gpu",
    "relever_memoire",
    "detecter_plateforme",
    "contraintes_plateforme",
    # Structures
    "ProfilMachine",
    "ContraintesPlateforme",
    "Gpu",
    "Memoire",
    "PiloteNvidia",
    "ReleveGpu",
    "Plateforme",
    "SourceMesureGpu",
    "SyntaxeGpuDocker",
    # Seuils mesurés
    "VERSION_PILOTE_MIN_BLACKWELL",
    "COMPUTE_MAJEUR_BLACKWELL",
    # API HTTP
    "routeur_system",
]
