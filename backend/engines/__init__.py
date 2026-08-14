"""Domaine `engines` — installer et gérer les moteurs d'inférence.

Deux moteurs, deux régimes opposés, et c'est structurant :

- **llama.cpp** (`llama-cpp-python`) est compilé avec le support CUDA au moment du build de
  l'image. Le domaine ne fait que **vérifier** sa présence et sa conformité : le binaire
  rapporte-t-il bien ses architectures CUDA et le contournement `FORCE_CUBLAS` ? Il ne le
  recompile jamais à l'exécution.
- **vLLM** est installé **à la demande**, dans un venv séparé par version. Ses dépendances (torch,
  CUDA 13) sont incompatibles avec celles du backend : les mélanger casse les deux. L'installation
  est annulable, ré-entrante, et n'est déclarée valide qu'après une sonde qui importe réellement
  vLLM dans le venv fraîchement construit.

Interface publique du domaine. Les autres domaines n'importent que d'ici — jamais `service`,
`llamacpp`, `vllm` ou leurs modules internes.

    from backend.engines import etat_des_moteurs, python_vllm, router

Le domaine `inference` utilise `python_vllm()` : il obtient l'interpréteur d'une installation
validée, ou une erreur explicite. Jamais un venv à moitié construit.
"""

from backend.engines.api import router
from backend.engines.modeles import (
    ARCHITECTURES_PARC,
    DiagnosticLlamaCpp,
    DiagnosticVllm,
    EtapeInstallation,
    EtatMoteurs,
    EvenementInstallation,
    MarqueurInstallation,
    NomMoteur,
    SanteMoteur,
    StatutMoteur,
    VersionVllm,
)
from backend.engines.service import (
    annuler_installation_vllm,
    etat_des_moteurs,
    installer_vllm,
    python_vllm,
    sante_llamacpp,
    sante_vllm,
    supprimer_version_vllm,
    versions_vllm,
)

__all__ = [
    # Routeur HTTP, à inclure sous le préfixe /api de l'application.
    "router",
    # Lecture d'état
    "etat_des_moteurs",
    "sante_llamacpp",
    "sante_vllm",
    "versions_vllm",
    # Cycle de vie des installations vLLM
    "installer_vllm",
    "annuler_installation_vllm",
    "supprimer_version_vllm",
    # Interface consommée par le domaine `inference`
    "python_vllm",
    # Modèles typés
    "ARCHITECTURES_PARC",
    "NomMoteur",
    "StatutMoteur",
    "SanteMoteur",
    "EtatMoteurs",
    "VersionVllm",
    "EtapeInstallation",
    "EvenementInstallation",
    "MarqueurInstallation",
    "DiagnosticLlamaCpp",
    "DiagnosticVllm",
]
