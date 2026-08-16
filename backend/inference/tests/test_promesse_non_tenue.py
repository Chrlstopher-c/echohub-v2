"""Preuve qu'une réponse close sur une annonce sans suite est relancée une fois.

Symptôme MESURÉ le 2026-08-16, socle renforcé DÉJÀ en place : le modèle cherche sur le web, cite
correctement ses sources, puis termine par « Je te l'ai intégré dans le simulateur. Voici le
fichier : » — et rien. Aucun appel d'outil dans ce tour, donc aucun fichier, et l'utilisateur ne
voit rien. La consigne du socle (« annoncer et faire sont deux actes distincts ») n'a pas suffi.

Le harnais ne devine pas une intention, mais il reconnaît une phrase LAISSÉE OUVERTE. C'est une
heuristique, et elle est volontairement étroite : relancer une réponse terminée coûterait un tour
entier à l'utilisateur, donc mieux vaut rater une promesse que d'en inventer une.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import backend.inference as domaine_inference
from backend.chat.modeles import ParametresEchantillonnage
from backend.chat.port_inference import MessageInference, RequeteGeneration
from backend.inference import MoteurChat
from backend.inference.engines_adapters.contrat import MessageChat, MorceauGeneration, OptionsGeneration
from backend.inference.reprise import CONSIGNE_PROMESSE, promesse_non_tenue
from backend.outils import registre
from backend.outils.contrat import ContexteExecution, DescriptionOutil, Outil

CONVERSATION = "conversation-promesse"


# --- reconnaissance d'une phrase laissée ouverte ------------------------------------------------


def test_un_deux_points_final_est_une_promesse() -> None:
    assert promesse_non_tenue("Je te l'ai intégré. Voici le fichier :")


def test_une_annonce_explicite_est_une_promesse() -> None:
    assert promesse_non_tenue("Parfait, voici la nouvelle version")
    assert promesse_non_tenue("Let me write the file")


def test_une_reponse_terminee_n_est_pas_une_promesse() -> None:
    """Le garde-fou qui compte : relancer une réponse finie coûte un tour entier à l'utilisateur."""
    assert not promesse_non_tenue("Le fichier est écrit et présenté ci-dessus.")
    assert not promesse_non_tenue("Je ne peux pas le faire : l'outil a échoué deux fois.")
    assert not promesse_non_tenue("")


# --- relance effective dans la boucle -----------------------------------------------------------


class _SuperviseurQuiPromet:
    """Promet sans agir au premier tour, puis répond normalement."""

    def __init__(self) -> None:
        self.tours = 0
        self.derniers_messages: list[MessageChat] = []

    def generer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
        outils: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[MorceauGeneration]:
        self.tours += 1
        self.derniers_messages = list(messages)
        return self._flux(promet=self.tours == 1)

    async def _flux(self, *, promet: bool) -> AsyncIterator[MorceauGeneration]:
        contenu = "Voici le fichier :" if promet else "C'est écrit, le voici."
        yield MorceauGeneration(type="token", contenu=contenu)
        yield MorceauGeneration(type="fin", raison_arret="stop")


def _outil_factice() -> Outil:
    async def executer(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
        return "fait"

    return Outil(
        description=DescriptionOutil(
            nom="ecrire_fichier", description="Outil de test.", parametres={"type": "object", "properties": {}}
        ),
        executer=executer,
    )


def _jouer(monkeypatch: Any, superviseur: Any, avec_outils: bool = True) -> str:
    monkeypatch.setattr(registre, "_OUTILS", {"ecrire_fichier": _outil_factice()} if avec_outils else {})
    monkeypatch.setattr(domaine_inference, "superviseur", superviseur)

    async def lire() -> str:
        morceaux: list[str] = []
        async for morceau in MoteurChat().generer(
            RequeteGeneration(
                messages=[MessageInference(role="user", contenu="écris-moi une page")],
                parametres=ParametresEchantillonnage(),
                conversation_id=CONVERSATION,
            )
        ):
            if isinstance(morceau.get("texte"), str):
                morceaux.append(morceau["texte"])
        return "".join(morceaux)

    return asyncio.run(lire())


def test_une_promesse_sans_appel_est_relancee(monkeypatch: Any) -> None:
    superviseur = _SuperviseurQuiPromet()

    texte = _jouer(monkeypatch, superviseur)

    assert superviseur.tours == 2, "le tour clos sur une annonce est relancé"
    assert "C'est écrit" in texte
    consignes = [m for m in superviseur.derniers_messages if str(m.content) == CONSIGNE_PROMESSE]
    assert consignes and consignes[0].role == "user"


def test_la_relance_n_a_lieu_qu_une_fois(monkeypatch: Any) -> None:
    """Un modèle qui promet indéfiniment ne doit pas faire tourner la boucle jusqu'à sa borne."""

    class _ToujoursPromet(_SuperviseurQuiPromet):
        def generer(self, messages, options, outils=None):  # type: ignore[no-untyped-def]
            self.tours += 1
            self.derniers_messages = list(messages)
            return self._flux(promet=True)

    superviseur = _ToujoursPromet()

    _jouer(monkeypatch, superviseur)

    assert superviseur.tours == 2, "une seule relance, puis on rend la main"


def test_aucune_relance_sans_registre_d_outils(monkeypatch: Any) -> None:
    """Sans outil, une annonce non tenue ne peut pas être réparée : relancer serait gratuit."""
    superviseur = _SuperviseurQuiPromet()

    _jouer(monkeypatch, superviseur, avec_outils=False)

    assert superviseur.tours == 1
