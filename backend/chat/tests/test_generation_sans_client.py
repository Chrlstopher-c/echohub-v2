"""Preuve qu'une génération survit au départ du client et se persiste quand même.

Défaut rapporté et reproduit le 2026-08-16, sur téléphone : l'utilisateur envoie son message, met
l'appareil en veille, et retrouve à son retour un message envoyé avec une réponse VIDE — sans savoir
si quelque chose tourne encore. Deux fois de suite.

La cause était structurelle. La boucle de génération vivait DANS le générateur du flux SSE : quand
le navigateur fermait la connexion — une mise en veille suffit — Starlette détruisait ce générateur,
`GeneratorExit` remontait, et la génération s'arrêtait net. Seul le texte déjà produit était
conservé, c'est-à-dire presque rien.

La connexion HTTP transporte désormais la réponse sans la conditionner : la production vit dans une
tâche que la déconnexion ne touche pas, et c'est elle qui persiste.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest

from backend.chat import depot, generation, port_inference
from backend.chat.modeles import DemandeGeneration, ResumeConversation
from backend.chat.port_inference import (
    ElementFlux,
    FragmentTexte,
    RequeteGeneration,
    StatistiquesGeneration,
)

TOTAL_FRAGMENTS = 6


class MoteurLent:
    """Rend ses fragments un par un, en cédant la main entre chacun.

    Le `sleep(0)` n'est pas décoratif : il donne à la boucle un point de reprise, donc au test la
    possibilité de couper le flux EN COURS de génération — exactement ce que fait une mise en veille.
    """

    def generer(self, requete: RequeteGeneration) -> AsyncIterator[ElementFlux]:
        return self._flux()

    async def _flux(self) -> AsyncIterator[ElementFlux]:
        for indice in range(TOTAL_FRAGMENTS):
            await asyncio.sleep(0)
            yield FragmentTexte(texte=f"morceau{indice} ")
        yield StatistiquesGeneration(tokens_generes=TOTAL_FRAGMENTS, tokens_par_seconde=12.0)


@pytest.fixture
def moteur_lent() -> Iterator[MoteurLent]:
    factice = MoteurLent()
    port_inference.definir_moteur(factice)
    yield factice
    port_inference.reinitialiser_moteur()


def _reponse_persistee(conversation_id: str) -> str:
    messages = [m for m in depot.lister_messages(conversation_id) if m.role == "assistant"]
    return messages[-1].contenu if messages else ""


def test_la_generation_se_termine_apres_le_depart_du_client(
    conversation: ResumeConversation, moteur_lent: MoteurLent
) -> None:
    """Le cas rapporté : le client part au milieu, la réponse doit être COMPLÈTE en base."""

    async def scenario() -> None:
        flux = generation.diffuser(
            generation.preparer(conversation.id, DemandeGeneration(contenu="bonjour"))
        )
        recus = 0
        async for _ in flux:
            recus += 1
            if recus == 3:  # début, puis deux fragments : on coupe en pleine génération
                break
        await flux.aclose()  # ce que fait Starlette quand la connexion tombe
        # La tâche de production doit poursuivre seule jusqu'au bout.
        for _ in range(200):
            if _reponse_persistee(conversation.id):
                break
            await asyncio.sleep(0.01)

    asyncio.run(scenario())

    persiste = _reponse_persistee(conversation.id)
    attendu = "".join(f"morceau{i} " for i in range(TOTAL_FRAGMENTS))
    assert persiste == attendu, "la réponse doit être entière, pas tronquée au départ du client"


def test_la_conversation_est_liberee_apres_le_depart_du_client(
    conversation: ResumeConversation, moteur_lent: MoteurLent
) -> None:
    """Sans libération, la conversation resterait bloquée : « une génération est déjà en cours »."""

    async def scenario() -> None:
        flux = generation.diffuser(
            generation.preparer(conversation.id, DemandeGeneration(contenu="bonjour"))
        )
        async for _ in flux:
            break
        await flux.aclose()
        for _ in range(200):
            if not generation.annulation.est_active(conversation.id):
                break
            await asyncio.sleep(0.01)

    asyncio.run(scenario())

    assert not generation.annulation.est_active(conversation.id)


def test_un_client_present_recoit_toujours_tout(
    conversation: ResumeConversation, moteur_lent: MoteurLent
) -> None:
    """Garde-fou : le découplage ne doit rien changer au cas normal, où personne ne se déconnecte."""

    async def lire() -> list[str]:
        textes: list[str] = []
        async for evenement in generation.diffuser(
            generation.preparer(conversation.id, DemandeGeneration(contenu="bonjour"))
        ):
            texte = getattr(evenement, "texte", None)
            if isinstance(texte, str):
                textes.append(texte)
        return textes

    textes = asyncio.run(lire())

    assert "".join(textes) == "".join(f"morceau{i} " for i in range(TOTAL_FRAGMENTS))
    assert _reponse_persistee(conversation.id) == "".join(f"morceau{i} " for i in range(TOTAL_FRAGMENTS))
