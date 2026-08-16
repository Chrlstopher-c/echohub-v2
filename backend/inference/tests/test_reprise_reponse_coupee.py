"""Preuve qu'une réponse coupée par la fenêtre est reprise jusqu'à être complète.

Défaut MESURÉ le 2026-08-16 sur un modèle réel (Qwen2.5-0.5B, contexte 2 048) : le moteur rend
1 973 tokens puis `finish_reason = "length"`. L'adaptateur le SAIT — il pose la raison sur son
morceau de fin — mais personne ne la lisait : la chaîne ne rendait que `texte`, `tokens_generes` et
`tokens_par_seconde`. La réponse s'arrêtait donc au milieu d'une phrase, en silence. Et quand la
coupure tombait en plein `<tool_call>`, le JSON devenait illisible, aucun appel n'était détecté, et
le balisage restait dans la réponse.

Le mécanisme est testé ici plutôt que le symptôme : un vrai modèle décide lui-même de sa longueur,
et deux tirages sur le même prompt ont donné 1 973 puis 610 tokens. Une reproduction en conditions
réelles ne ferait donc pas un test de régression fiable — c'est exactement ce que la mesure a montré.

La distinction qui compte, et qui est vérifiée ici : `length` recouvre deux causes que le moteur ne
sépare pas. Fenêtre pleine — subi, on reprend. Plafond demandé par l'utilisateur — voulu, on
s'arrête. Les confondre reviendrait à passer outre un réglage posé exprès.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import backend.inference as domaine_inference
from backend.chat.modeles import ParametresEchantillonnage
from backend.chat.port_inference import MessageInference, RequeteGeneration
from backend.inference import (
    AVERTISSEMENT_FENETRE_PLEINE,
    CONTINUATIONS_MAX,
    MoteurChat,
)
from backend.inference.engines_adapters.contrat import (
    MessageChat,
    MorceauGeneration,
    OccupationContexte,
    OptionsGeneration,
)
from backend.outils import registre

CONVERSATION = "conversation-reprise"


class _SuperviseurCoupe:
    """Coupe ses `coupures` premiers tours par `length`, puis termine normalement.

    Retient les messages de chaque tour : c'est ainsi qu'on vérifie que la reprise repart du texte
    déjà produit, et non d'une nouvelle réponse.
    """

    def __init__(self, coupures: int = 1, tokens_libres: int | None = 4096) -> None:
        self.coupures = coupures
        self.tours = 0
        self.messages_par_tour: list[list[MessageChat]] = []
        self._tokens_libres = tokens_libres

    def generer(
        self,
        messages: Sequence[MessageChat],
        options: OptionsGeneration,
        outils: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[MorceauGeneration]:
        self.tours += 1
        self.messages_par_tour.append(list(messages))
        return self._flux(coupe=self.tours <= self.coupures, indice=self.tours)

    async def _flux(self, *, coupe: bool, indice: int) -> AsyncIterator[MorceauGeneration]:
        yield MorceauGeneration(type="token", contenu=f"morceau{indice} ")
        yield MorceauGeneration(type="fin", raison_arret="length" if coupe else "stop")

    async def compter_contexte(self, prompt_systeme: str, messages: Sequence[MessageChat]) -> OccupationContexte:
        if self._tokens_libres is None:
            return OccupationContexte(mesurable=False, raison="aucun tokenizer")
        return OccupationContexte(mesurable=True, contexte_total=8192, tokens_libres=self._tokens_libres)


def _jouer(monkeypatch: Any, superviseur: _SuperviseurCoupe, max_tokens: int | None = None) -> str:
    monkeypatch.setattr(registre, "_OUTILS", {})
    monkeypatch.setattr(domaine_inference, "superviseur", superviseur)

    async def lire() -> str:
        morceaux: list[str] = []
        async for morceau in MoteurChat().generer(
            RequeteGeneration(
                messages=[MessageInference(role="user", contenu="écris un texte long")],
                parametres=ParametresEchantillonnage(max_tokens=max_tokens),
                conversation_id=CONVERSATION,
            )
        ):
            if isinstance(morceau.get("texte"), str):
                morceaux.append(morceau["texte"])
        return "".join(morceaux)

    return asyncio.run(lire())


def test_une_reponse_coupee_par_la_fenetre_est_reprise(monkeypatch: Any) -> None:
    superviseur = _SuperviseurCoupe(coupures=1)

    texte = _jouer(monkeypatch, superviseur)

    assert superviseur.tours == 2, "le tour coupé est repris, il n'est pas rendu tel quel"
    assert texte == "morceau1 morceau2 ", "la reprise s'ajoute au texte, elle ne le remplace pas"
    assert AVERTISSEMENT_FENETRE_PLEINE not in texte


def test_une_reponse_complete_n_est_pas_reprise(monkeypatch: Any) -> None:
    """Garde-fou : à trop vouloir reprendre, on relancerait le moteur après chaque réponse."""
    superviseur = _SuperviseurCoupe(coupures=0)

    texte = _jouer(monkeypatch, superviseur)

    assert superviseur.tours == 1
    assert texte == "morceau1 "


def test_la_reprise_repart_du_texte_deja_produit(monkeypatch: Any) -> None:
    """Sans le partiel dans le prompt, le modèle recommencerait au lieu de continuer."""
    superviseur = _SuperviseurCoupe(coupures=1)

    _jouer(monkeypatch, superviseur)

    second = superviseur.messages_par_tour[1]
    assert second[-2].role == "assistant" and "morceau1" in str(second[-2].content)
    assert second[-1].role == "user", "la consigne de reprise suit le partiel"
    assert "Continue" in str(second[-1].content)


def test_un_plafond_demande_par_l_utilisateur_est_respecte(monkeypatch: Any) -> None:
    """`length` au plafond demandé est un arrêt VOULU : le contourner ignorerait le réglage."""
    superviseur = _SuperviseurCoupe(coupures=1)

    texte = _jouer(monkeypatch, superviseur, max_tokens=256)

    assert superviseur.tours == 1, "aucune reprise quand un plafond a été demandé"
    assert texte == "morceau1 "


def test_une_fenetre_pleine_est_dite_a_l_utilisateur(monkeypatch: Any) -> None:
    """Reprendre sans place ne produirait rien : on le dit, avec une remédiation qui existe."""
    superviseur = _SuperviseurCoupe(coupures=9, tokens_libres=12)

    texte = _jouer(monkeypatch, superviseur)

    assert superviseur.tours == 1, "aucune reprise à vide quand la fenêtre est pleine"
    assert AVERTISSEMENT_FENETRE_PLEINE in texte
    assert "contexte plus grand" in texte, "la remédiation est nommée, pas seulement le symptôme"


def test_les_reprises_sont_bornees(monkeypatch: Any) -> None:
    """Un moteur qui couperait indéfiniment ne doit pas faire boucler la génération sans fin."""
    superviseur = _SuperviseurCoupe(coupures=99)

    texte = _jouer(monkeypatch, superviseur)

    assert superviseur.tours == CONTINUATIONS_MAX + 1
    assert AVERTISSEMENT_FENETRE_PLEINE in texte, "la réponse reste incomplète, et elle le dit"


def test_une_mesure_indisponible_ne_coupe_pas_la_reponse(monkeypatch: Any) -> None:
    """Un comptage absent ne doit pas décider à la place du moteur qu'une réponse est finie."""
    superviseur = _SuperviseurCoupe(coupures=1, tokens_libres=None)

    texte = _jouer(monkeypatch, superviseur)

    assert superviseur.tours == 2
    assert texte == "morceau1 morceau2 "
