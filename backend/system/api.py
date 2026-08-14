"""Exposition HTTP du domaine `system`.

Une seule route : le profil machine mesuré à l'instant de l'appel. L'interface le rafraîchit quand
elle a besoin d'une valeur fraîche, elle ne le conserve pas — et surtout elle n'en dérive aucune
décision, c'est le rôle du planificateur.

Le préfixe `/api` est ajouté par l'assemblage de l'application, pas ici.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.system.modeles import ProfilMachine
from backend.system.profil import profil_machine

routeur = APIRouter(prefix="/system", tags=["system"])


# Route synchrone volontairement : la mesure peut lancer un sous-processus (nvidia-smi) et bloquer
# jusqu'à quelques secondes. FastAPI l'exécute alors dans son pool de threads, sans figer la boucle.
@routeur.get("/profil", response_model=ProfilMachine, summary="Profil matériel mesuré maintenant")
def lire_profil() -> ProfilMachine:
    """Mesure et retourne l'état matériel courant : plateforme, contraintes, GPU, VRAM, RAM."""
    return profil_machine()
