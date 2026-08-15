"""Routes HTTP du domaine `outils`.

Une seule route : le texte des limites réelles du bac à sable (plan d'exécution, section 2.6),
destiné à être affiché à l'utilisateur — l'interface le rend tel quel, elle ne le réécrit ni ne
l'embellit. Aucune route d'exécution ici : les outils ne sont appelés que par le modèle, via le
registre (`backend/outils/registre.py`), jamais depuis le web.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.outils import LIMITES_REELLES_TEXTE


# Sans préfixe `/api` : comme les autres domaines (`backend.chat.routes`, `backend.fichiers.routes`),
# c'est nginx (production) ou le proxy Vite (développement) qui porte ce préfixe et le retire avant
# d'atteindre l'application — jamais codé ici (`main.py`, en-tête du fichier).
routeur = APIRouter(prefix="/outils", tags=["outils"])


@routeur.get("/limites-bac")
async def limites_bac() -> dict[str, str]:
    """Texte prêt à afficher, écrit une fois côté backend — la seule source, pour que l'interface
    ne puisse jamais diverger de ce que le bac à sable garantit réellement."""
    return {"texte": LIMITES_REELLES_TEXTE}
