"""Conduite de la boucle d'outils — réglable, et deux conduites nommées.

Le harnais, ce n'est pas la liste des outils : c'est ce que la boucle FAIT autour d'eux — combien
de tours elle accorde, quand elle relance, quand elle considère que le modèle tourne en rond. Les
outils restent une source unique (`backend/outils/registre.py`) ; ce module ne décide que de la
conduite. Cette séparation est ce qui rend la comparaison possible : à outils constants et modèle
constant, la seule variable est la conduite, donc un écart lui est attribuable.

DEUX CONDUITES

`echohub` est la conduite d'origine, inchangée : six tours d'outils, une relance sur promesse non
tenue, l'anti-redite sur appel échoué. Elle reste le défaut — un changement de défaut modifierait
le comportement de conversations existantes sans que personne l'ait demandé.

`forge` vient du harnais d'évaluation d'agent-forge, et n'ajoute que ce qui a été mesuré comme
manquant. Trois écarts, pas un de plus :

1. VINGT tours au lieu de six. Six suffit à un aller-retour outil ; une tâche en cascade — lire un
   fichier qui désigne le suivant, quatre niveaux, puis vérifier — les épuise avant d'arriver au
   bout. Mesuré le 2026-08-26 sur la famille `cascade` d'agent-forge : les tâches utiles tiennent
   entre onze et vingt-quatre tours. Une borne atteinte ne mesure plus le modèle, elle mesure la
   borne.

2. RELANCE SUR TOUR MUET. `promesse_non_tenue` écarte le tour vide par construction
   (`if not fin: return False`) : elle cherche une annonce, et un tour vide n'annonce rien. Le cas
   existe pourtant — mesuré le 2026-08-25 sur la webapp d'agent-forge, où le modèle rendait un tour
   de raisonnement pur, sans un mot de réponse. Les deux détections sont complémentaires, jamais
   redondantes : l'une regarde ce qui a été promis, l'autre qu'il y ait quelque chose.

3. ANTI-RADOTAGE SUR LE TEXTE. L'anti-redite d'origine (`_REDITE`) borne les APPELS échoués
   identiques. Elle ne voit pas un modèle qui réécrit trois fois le même paragraphe sans jamais
   appeler d'outil — mesuré le 2026-08-25, et invisible précisément parce que la détection ne
   regardait que les appels. Deux tours consécutifs au texte identique suffisent à le dire.

Ce que `forge` NE change PAS, et c'est délibéré : l'anti-redite sur appels, la consigne de clôture
quand rien n'a abouti, la reprise sur troncature. Ces trois mécanismes sont mesurés et bons ; les
remplacer par nos équivalents aurait été du remplacement, pas du portage.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

# Sous ce seuil, un tour est tenu pour muet : le modèle n'a pas répondu, il a seulement réfléchi.
# Quarante caractères, parce qu'une vraie réponse courte — « Oui, la version 3.12 le permet. » —
# les dépasse, alors qu'un fragment resté en suspens ne les atteint pas. Mesuré sur la webapp
# d'agent-forge : abaisser à zéro laissait passer les tours de raisonnement pur, monter à cent
# relançait des réponses complètes.
MIN_REPONSE_CARACTERES = 40

# Deux tours consécutifs identiques suffisent. Trois laissait l'utilisateur regarder la même
# réponse s'écrire une fois de trop avant que le harnais ne réagisse.
RADOTAGE_TOURS = 2

# Comparaison sur le texte normalisé : un modèle qui radote ne recopie pas au caractère près, il
# reproduit la même phrase avec une ponctuation ou une espace de différence.
_NORMALISATION = re.compile(r"\s+")


class Harnais(BaseModel):
    """Réglages de conduite d'une boucle d'outils. Immuable : c'est une constante nommée."""

    model_config = ConfigDict(frozen=True)

    nom: str
    tours_outils_max: int = Field(ge=1, le=60)
    # Relancer un tour qui n'a produit ni appel ni réponse lisible. Distinct de la relance sur
    # promesse : celle-ci cherche une annonce, celle-là cherche l'absence de tout.
    relance_sur_tour_muet: bool = False
    relances_muettes_max: int = Field(default=1, ge=0, le=3)
    # 0 désactive la détection de radotage textuel.
    radotage_tours: int = Field(default=0, ge=0, le=5)


ECHOHUB = Harnais(nom="echohub", tours_outils_max=6)

FORGE = Harnais(
    nom="forge",
    tours_outils_max=20,
    relance_sur_tour_muet=True,
    relances_muettes_max=2,
    radotage_tours=RADOTAGE_TOURS,
)

_CONNUS: dict[str, Harnais] = {ECHOHUB.nom: ECHOHUB, FORGE.nom: FORGE}
DEFAUT = ECHOHUB

CONSIGNE_TOUR_MUET = (
    "Your last turn produced nothing: no tool call, and no answer to the user — only reasoning, "
    "which the user does not see. Answer NOW, in French, with what you have. If you need a tool, "
    "call it in this turn with every argument inline."
)

CONSIGNE_RADOTAGE = (
    "You have just written the same thing twice in a row. Repeating it a third time will not help "
    "the user. Either do something different — call a tool, ask a precise question — or say "
    "plainly what is blocking you and stop."
)


def choisir(nom: str | None) -> Harnais:
    """Harnais nommé, ou le défaut. Un nom inconnu retombe sur le défaut plutôt que d'échouer.

    La valeur vient d'une requête HTTP, donc d'une entrée non fiable — et, quand une conversation
    est rejouée, d'un enregistrement écrit par une version antérieure qui pouvait connaître un nom
    disparu depuis. Refuser la génération pour un nom de conduite serait une panne là où il y a une
    valeur par défaut parfaitement valable.
    """
    if not nom:
        return DEFAUT
    return _CONNUS.get(nom.strip().lower(), DEFAUT)


def noms_connus() -> list[str]:
    """Conduites proposables à l'interface, dans l'ordre : le défaut d'abord."""
    return [DEFAUT.nom] + [nom for nom in _CONNUS if nom != DEFAUT.nom]


def tour_muet(texte: str, harnais: Harnais) -> bool:
    """Ce tour n'a-t-il produit aucune réponse lisible ?

    Appelée seulement quand le tour n'a demandé AUCUN outil : un tour qui appelle un outil n'a pas
    à répondre, son travail est l'appel. Confondre les deux relançait des tours parfaitement
    normaux — mesuré le 2026-08-25, deux corrections successives avant d'arriver à ce critère.
    """
    if not harnais.relance_sur_tour_muet:
        return False
    return len(texte.strip()) < MIN_REPONSE_CARACTERES


def _normaliser(texte: str) -> str:
    return _NORMALISATION.sub(" ", texte.strip().lower())


def radote(tours_precedents: list[str], harnais: Harnais) -> bool:
    """Les derniers tours répètent-ils le même texte ?

    `tours_precedents` porte les textes rendus, le plus récent en dernier. La comparaison se fait
    sur la forme normalisée : un radotage reproduit la phrase, pas nécessairement les espaces.
    Un tour vide ne compte jamais comme une répétition — c'est `tour_muet` qui le traite, et deux
    tours vides seraient sinon comptés comme un radotage, avec la mauvaise consigne à la clé.
    """
    seuil = harnais.radotage_tours
    if seuil < 2 or len(tours_precedents) < seuil:
        return False
    derniers = [_normaliser(texte) for texte in tours_precedents[-seuil:]]
    if not derniers[-1]:
        return False
    return all(texte == derniers[-1] for texte in derniers)


__all__ = [
    "CONSIGNE_RADOTAGE",
    "CONSIGNE_TOUR_MUET",
    "DEFAUT",
    "ECHOHUB",
    "FORGE",
    "Harnais",
    "choisir",
    "noms_connus",
    "radote",
    "tour_muet",
]
