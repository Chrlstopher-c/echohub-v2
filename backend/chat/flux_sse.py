"""Encodage Server-Sent Events des événements de génération.

Un module séparé parce que le format du fil est une décision de transport, pas de domaine : la
génération produit des événements typés, ce fichier décide comment ils voyagent.

Chaque trame porte à la fois un champ `event:` et un champ `type` dans sa charge JSON. Ce n'est pas
un doublon gratuit : `EventSource` route sur `event:`, tandis qu'un client `fetch` + `ReadableStream`
— ce que fait le frontend pour pouvoir annuler la requête — parse le JSON et n'a que `type` sous la
main. Les deux consommations restent possibles sans code conditionnel.
"""

from __future__ import annotations

from backend.chat.modeles import EvenementFlux

# `X-Accel-Buffering` désactive la mise en tampon de nginx, qui sert le frontend et proxifie l'API :
# sans lui, le proxy retient les fragments et le streaming ne se voit plus côté navigateur.
ENTETES_SSE: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

TYPE_MEDIA_SSE = "text/event-stream"


def encoder(evenement: EvenementFlux) -> str:
    """Sérialise un événement en une trame SSE complète.

    Le JSON produit par pydantic échappe les sauts de ligne, ce qui garantit une charge sur une
    seule ligne — condition nécessaire pour que la trame reste valide.
    """
    return f"event: {evenement.type}\ndata: {evenement.model_dump_json()}\n\n"
