"""Un tour complet, du réglage jusqu'au message persisté, avec un moteur factice.

Aucun GPU, aucun réseau, aucun navigateur : le port d'inférence accepte n'importe quel objet
conforme, ce qui rend la chaîne vérifiable en mémoire. Ce que ces cas prouvent : les réglages de la
conversation arrivent bien au moteur, et la réponse générée se range dans la bonne branche.

Les coroutines sont pilotées par `asyncio.run` plutôt que par un marqueur `pytest.mark.asyncio` :
le dépôt ne configure nulle part `asyncio_mode`, et un test ne doit pas dépendre d'une
configuration absente.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest

from backend.chat import depot, generation, port_inference
from backend.chat.modeles import (
    DemandeGeneration,
    DemandeRejeu,
    EvenementDebut,
    EvenementFin,
    EvenementFlux,
    ParametresEchantillonnage,
    ReglagesConversation,
    ResumeConversation,
)
from backend.chat.port_inference import (
    ElementFlux,
    FragmentTexte,
    RequeteGeneration,
    StatistiquesGeneration,
)


class MoteurFactice:
    """Moteur minimal conforme au port : mémorise la requête reçue, rend deux fragments et ses mesures."""

    def __init__(self) -> None:
        self.recue: RequeteGeneration | None = None

    def generer(self, requete: RequeteGeneration) -> AsyncIterator[ElementFlux]:
        self.recue = requete
        return self._flux()

    async def _flux(self) -> AsyncIterator[ElementFlux]:
        yield FragmentTexte(texte="re")
        yield FragmentTexte(texte="bonjour")
        yield StatistiquesGeneration(tokens_generes=2, tokens_par_seconde=8.0)


@pytest.fixture
def moteur() -> Iterator[MoteurFactice]:
    """Branche un moteur factice sur le domaine, et le débranche après le cas."""
    factice = MoteurFactice()
    port_inference.definir_moteur(factice)
    yield factice
    port_inference.reinitialiser_moteur()


def diffuser(preparation: generation.PreparationGeneration) -> list[EvenementFlux]:
    """Consomme tout le flux et rend les événements émis, dans l'ordre."""

    async def lire() -> list[EvenementFlux]:
        return [evenement async for evenement in generation.diffuser(preparation)]

    return asyncio.run(lire())


def test_les_reglages_arrivent_au_moteur(conversation: ResumeConversation, moteur: MoteurFactice) -> None:
    parametres = ParametresEchantillonnage(
        temperature=0.3,
        top_p=0.7,
        top_k=11,
        penalite_repetition=1.25,
        max_tokens=12345,
        sequences_arret=["<|fin|>"],
        graine=99,
    )
    depot.ecrire_reglages(conversation.id, ReglagesConversation(prompt_systeme="Sois bref.", parametres=parametres))

    diffuser(generation.preparer(conversation.id, DemandeGeneration(contenu="bonjour")))

    assert moteur.recue is not None
    assert moteur.recue.parametres == parametres
    assert moteur.recue.messages[0].role == "system"


def test_max_tokens_absent_reste_absent_jusqu_au_moteur(
    conversation: ResumeConversation, moteur: MoteurFactice
) -> None:
    """Aucun plafond n'est fabriqué en chemin : le moteur reçoit `None` et décide avec sa fenêtre."""
    diffuser(generation.preparer(conversation.id, DemandeGeneration(contenu="bonjour")))
    assert moteur.recue is not None
    assert moteur.recue.parametres.max_tokens is None


def test_reponse_persistee_dans_la_branche_ouverte(conversation: ResumeConversation, moteur: MoteurFactice) -> None:
    diffuser(generation.preparer(conversation.id, DemandeGeneration(contenu="bonjour")))
    premiere = depot.lister_messages(conversation.id)
    assert [m.contenu for m in premiere] == ["bonjour", "rebonjour"]
    assert premiere[1].tokens_generes == 2

    rejeu = generation.preparer_rejeu(conversation.id, premiere[1].id, DemandeRejeu())
    evenements = diffuser(rejeu)

    debut = evenements[0]
    assert isinstance(debut, EvenementDebut)
    assert debut.parent_id == premiere[0].id
    assert debut.message_utilisateur_id is None
    assert isinstance(evenements[-1], EvenementFin)

    arbre = depot.lire_arbre(conversation.id)
    assert len(arbre.messages) == 3
    chemin = depot.lire_branche(conversation.id)
    assert [m.id for m in chemin.messages] == [premiere[0].id, debut.message_id]
    assert chemin.variantes[debut.message_id] == [premiere[1].id, debut.message_id]
