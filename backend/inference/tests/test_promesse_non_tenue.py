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
from backend.inference.reprise import (
    CONSIGNE_CLOTURE_PROMESSE,
    CONSIGNE_PROMESSE,
    CONSIGNES_PROMESSE,
    RELANCES_PROMESSE_MAX,
    promesse_non_tenue,
)
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
        # Tous les messages vus, tous tours confondus : le tour de clôture reconstruit sa propre
        # liste, donc n'inspecter que le dernier ferait manquer les consignes des tours précédents.
        self.messages_vus: list[MessageChat] = []

    def generer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
        outils: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[MorceauGeneration]:
        self.tours += 1
        self.derniers_messages = list(messages)
        self.messages_vus += list(messages)
        return self._flux(promet=self.tours == 1)

    async def _flux(self, *, promet: bool) -> AsyncIterator[MorceauGeneration]:
        # Textes assez longs pour ne PAS tomber sous `MIN_REPONSE_CARACTERES` : sous ce seuil le
        # tour est classé muet, une autre cause avec sa propre consigne, et ce test ne prouverait
        # plus rien sur les promesses.
        contenu = (
            "J'ai rassemblé tout ce qu'il faut et je te prépare le fichier complet maintenant, "
            "avec la structure demandée. Voici le fichier :"
            if promet else
            "C'est écrit, le voici — le fichier a été produit et déposé dans la conversation, "
            "tu peux l'ouvrir directement depuis le panneau latéral."
        )
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

    # Trois tours : l'annonce, la relance qui la répare, puis le tour final sans outil. Le stub
    # tient sa promesse dès la relance — c'est le cas nominal, celui qui n'a jamais posé problème.
    assert superviseur.tours >= 2, "le tour clos sur une annonce est relancé"
    assert "C'est écrit" in texte
    consignes = [m for m in superviseur.messages_vus if str(m.content) == CONSIGNE_PROMESSE]
    assert consignes and consignes[0].role == "user"


def test_les_relances_sont_bornees_et_escaladent(monkeypatch: Any) -> None:
    """Un modèle qui promet indéfiniment ne doit pas faire tourner la boucle jusqu'à sa borne.

    Porté de 1 à 3 relances le 2026-08-26 : le journal de production montrait la relance partir, le
    modèle RÉ-ANNONCER, et la boucle rendre la main sur cette seconde annonce. Trois rappels, mais
    trois rappels DIFFÉRENTS — répéter le même dans un contexte qui le contient déjà revient à
    redemander à l'identique ce que le modèle vient de ne pas faire.
    """

    class _ToujoursPromet(_SuperviseurQuiPromet):
        def __init__(self) -> None:
            super().__init__()
            self.consignes_vues: list[str] = []

        def generer(self, messages, options, outils=None):  # type: ignore[no-untyped-def]
            self.tours += 1
            self.derniers_messages = list(messages)
            self.consignes_vues += [
                str(m.content) for m in messages
                if m.role == "user" and str(m.content) in CONSIGNES_PROMESSE
            ]
            return self._promesse_variee(self.tours)

        async def _promesse_variee(self, tour):  # type: ignore[no-untyped-def]
            # Texte DIFFÉRENT à chaque tour : c'est ainsi qu'un modèle ré-annonce réellement. Un
            # texte répété au mot près relève du radotage, qui a sa propre cause et son propre
            # quota — le confondre ici testerait autre chose que ce que ce test prétend prouver.
            yield MorceauGeneration(type="token", contenu=f"Je vais écrire le fichier {tour} :")
            yield MorceauGeneration(type="fin", raison_arret="stop")

    superviseur = _ToujoursPromet()

    _jouer(monkeypatch, superviseur)

    # Ce qui compte n'est pas le nombre exact de tours — la clôture en ajoute selon la conduite —
    # mais que les TROIS consignes de promesse aient été posées, et qu'elles soient DISTINCTES.
    # Trois fois le même rappel était précisément l'ancien comportement inefficace.
    assert len(set(superviseur.consignes_vues)) == RELANCES_PROMESSE_MAX, "consignes répétées"
    assert superviseur.tours > RELANCES_PROMESSE_MAX, "toutes les relances n'ont pas été jouées"


def test_une_promesse_a_bout_de_relances_declenche_une_cloture(monkeypatch: Any) -> None:
    """Le défaut vu par l'utilisateur : « Je vais créer les fichiers […] : », puis plus rien.

    Rendre la main ici laissait une phrase en suspens. Le dernier tour part donc SANS outil, avec
    une consigne qui ne demande plus d'agir mais de rendre compte — la seule chose encore possible.
    """

    class _ToujoursPromet(_SuperviseurQuiPromet):
        def __init__(self) -> None:
            super().__init__()
            self.outils_du_dernier_tour: object = "jamais appelé"

        def generer(self, messages, options, outils=None):  # type: ignore[no-untyped-def]
            self.tours += 1
            self.derniers_messages = list(messages)
            self.outils_du_dernier_tour = outils
            return self._promesse_variee(self.tours)

        async def _promesse_variee(self, tour):  # type: ignore[no-untyped-def]
            yield MorceauGeneration(type="token", contenu=f"Je vais écrire le fichier {tour} :")
            yield MorceauGeneration(type="fin", raison_arret="stop")

    superviseur = _ToujoursPromet()

    _jouer(monkeypatch, superviseur)

    assert superviseur.outils_du_dernier_tour is None, "le tour de clôture déclare encore des outils"
    cloture = [m for m in superviseur.derniers_messages
               if str(m.content) == CONSIGNE_CLOTURE_PROMESSE]
    assert cloture, "la consigne de clôture n'a pas été posée"


def test_aucune_relance_sans_registre_d_outils(monkeypatch: Any) -> None:
    """Sans outil, une annonce non tenue ne peut pas être réparée : relancer serait gratuit."""
    superviseur = _SuperviseurQuiPromet()

    _jouer(monkeypatch, superviseur, avec_outils=False)

    assert superviseur.tours == 1


class _PrometPuisAgitPuisPromet:
    """Promet, agit quand on le relance, puis referme sur une SECONDE promesse.

    Comportement réel mesuré le 2026-08-16 : relancé une fois, le modèle écrit son fichier, puis
    termine par « Le voici : » sans appeler `presenter_fichier`. Un compteur global de relances
    laissait passer cette seconde promesse alors qu'un travail réel venait d'avoir lieu.
    """

    def __init__(self) -> None:
        self.tours = 0

    def generer(self, messages, options, outils=None):  # type: ignore[no-untyped-def]
        self.tours += 1
        return self._flux(self.tours)

    async def _flux(self, tour: int) -> AsyncIterator[MorceauGeneration]:
        if tour == 1:
            contenu = "Voici le fichier :"           # promesse -> relance 1
        elif tour == 2:
            contenu = '<tool_call>{"name": "ecrire_fichier", "arguments": {}}</tool_call>'
        elif tour == 3:
            contenu = "Le voici :"                   # promesse APRÈS un outil abouti -> relance 2
        else:
            contenu = "Le fichier est présenté ci-dessus."
        yield MorceauGeneration(type="token", contenu=contenu)
        yield MorceauGeneration(type="fin", raison_arret="stop")


def test_un_outil_abouti_redonne_droit_a_une_relance(monkeypatch: Any) -> None:
    superviseur = _PrometPuisAgitPuisPromet()

    texte = _jouer(monkeypatch, superviseur)

    assert superviseur.tours == 5, "la promesse qui suit un travail réel est relancée elle aussi"
    assert "présenté ci-dessus" in texte, "le tour final n'est plus une promesse"
