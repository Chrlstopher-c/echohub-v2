"""Sous-domaine vLLM : venvs isolés, installation annulable, état de santé.

Interface publique du sous-domaine. Le reste de l'application passe par `backend.engines`, jamais
directement par `installation`, `venvs` ou `etat`.
"""

from backend.engines.vllm.etat import inventaire_verifie, python_de_version, sante, version_active
from backend.engines.vllm.installation import annuler, installations_en_cours, installer
from backend.engines.vllm.venvs import inventaire, supprimer, valider_version

__all__ = [
    "annuler",
    "installations_en_cours",
    "installer",
    "inventaire",
    "inventaire_verifie",
    "python_de_version",
    "sante",
    "supprimer",
    "valider_version",
    "version_active",
]
