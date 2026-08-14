"""Sous-domaine llama.cpp : vérification de présence et de santé du binaire compilé.

Interface publique du sous-domaine. Le reste de l'application passe par `backend.engines`, jamais
directement par `diagnostic` ni par `sonde`.
"""

from backend.engines.llamacpp.diagnostic import diagnostiquer, sante

__all__ = ["diagnostiquer", "sante"]
