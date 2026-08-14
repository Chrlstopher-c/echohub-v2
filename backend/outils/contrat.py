"""Contrat d'un outil — ce que le modèle voit, et ce que le harnais exécute.

Le format est celui d'OpenAI (`type: function`), parce que c'est celui que les gabarits de nos
modèles attendent : les templates Jinja des GGUF chargés ici itèrent sur `tools` en lisant
`function.name`, `function.description` et `function.parameters`. Vérifié le 2026-08-14 sur les six
modèles présents — tous portent `tools` et `tool_call` dans leur gabarit.

Un outil est une fonction pure du point de vue du harnais : il reçoit des arguments validés, il
rend un texte destiné à repartir dans le contexte du modèle. Il ne décide jamais de la suite de la
conversation, et il ne parle jamais à l'utilisateur directement.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

# Le résultat d'un outil repart dans le contexte : sans borne, une page web de 200 Ko ferait sauter
# la fenêtre du modèle et supprimerait l'historique de la conversation. Tronquer est visible et
# réparable ; déborder ne l'est pas.
LONGUEUR_RESULTAT_MAX = 8_000


class DescriptionOutil(BaseModel):
    """Déclaration d'un outil au format attendu par les gabarits de conversation."""

    nom: str = Field(min_length=1)
    description: str = Field(min_length=1)
    # Schéma JSON des arguments. Rendu tel quel au modèle : c'est lui qui contraint ce qu'il émet.
    parametres: dict[str, Any]

    def vers_format_moteur(self) -> dict[str, Any]:
        """Forme exacte attendue dans `tools=` par `create_chat_completion`."""
        return {
            "type": "function",
            "function": {
                "name": self.nom,
                "description": self.description,
                "parameters": self.parametres,
            },
        }


class ResultatOutil(BaseModel):
    """Ce qui repart au modèle après l'exécution.

    Un échec est un résultat comme un autre : le modèle doit l'apprendre pour pouvoir corriger son
    tir ou l'annoncer à l'utilisateur. Masquer l'erreur produirait une invention à la place.
    """

    nom: str
    succes: bool
    texte: str
    # Conservé pour l'affichage : l'interface montre ce que le modèle a réellement demandé.
    arguments: dict[str, Any] = Field(default_factory=dict)

    def tronque(self) -> ResultatOutil:
        if len(self.texte) <= LONGUEUR_RESULTAT_MAX:
            return self
        coupe = self.texte[:LONGUEUR_RESULTAT_MAX]
        return self.model_copy(update={"texte": f"{coupe}\n\n[résultat tronqué à {LONGUEUR_RESULTAT_MAX} caractères]"})


# Un outil s'exécute de façon asynchrone : le seul outil du MVP fait un appel réseau, et bloquer la
# boucle pendant une recherche gèlerait toutes les autres requêtes de l'application.
Execution = Callable[[dict[str, Any]], Awaitable[str]]


class Outil(BaseModel):
    """Un outil disponible : sa déclaration et son exécution."""

    model_config = {"arbitrary_types_allowed": True}

    description: DescriptionOutil
    executer: Execution

    @property
    def nom(self) -> str:
        return self.description.nom
