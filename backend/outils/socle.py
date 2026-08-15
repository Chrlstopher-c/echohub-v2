"""Socle de prompt système — posé AVANT tout prompt venu de l'interface.

Raison d'être, constatée et non supposée : sans outils déclarés, les modèles chargés ici annoncent
spontanément qu'ils savent chercher sur le web, puis inventent des résultats. Relevé le
2026-08-14 — « Oui, je peux effectuer des recherches web » suivi d'une réponse entièrement
fabriquée. Le socle existe pour supprimer cet écart entre ce que le modèle croit pouvoir faire et
ce que le harnais lui donne réellement.

Deux principes gouvernent ce fichier :

- le socle énonce des FAITS sur l'environnement (quels outils existent, ce qu'ils rendent), jamais
  une personnalité. Le caractère de l'assistant appartient au prompt de la conversation, que
  l'utilisateur écrit et modifie ;
- le socle ne peut pas être écrasé par le prompt de la conversation : les deux sont concaténés,
  socle d'abord. Un prompt utilisateur qui dirait le contraire ne supprime pas les faits — il
  entrerait en contradiction avec eux, et c'est au modèle de trancher, pas au harnais de mentir.

Sans aucun outil disponible, le socle dit l'inverse : aucune capacité externe. C'est le cas le plus
important, parce que c'est celui où le modèle affabule.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.outils.contrat import DescriptionOutil

_SANS_OUTIL = """Tu tournes en local, sans aucun accès extérieur : ni web, ni fichiers, ni exécution de code.
Tu ne peux donc pas chercher, ouvrir un lien, lire un document ni vérifier une information.
Si on te demande quelque chose qui l'exigerait, dis-le simplement au lieu de faire semblant.
Ne prétends jamais avoir consulté une source : cite de mémoire en le signalant, ou reconnais que tu ne sais pas.
Ta date d'entraînement est dépassée : sur l'actualité, préviens que tes informations peuvent être périmées."""

_AVEC_OUTILS = """Tu tournes en local et tu disposes des outils listés ci-dessous. Ce sont tes SEULES capacités
extérieures : tout ce qui n'y figure pas, tu ne peux pas le faire.

Quand NE PAS appeler d'outil :
- Quand tu sais déjà faire — écrire du code, traduire, reformuler, calculer, raisonner. Un outil
  n'y ajoute rien et fait attendre l'utilisateur pour rien.
- Dans une conversation ordinaire, ou pour une question qui te concerne toi.

Le partage est celui-ci : un doute sur un FAIT justifie une recherche, un doute sur ta capacité à
rédiger n'en justifie aucune. Vérifier une notion que tu connais mal est légitime et préférable à
l'inventer ; chercher par réflexe avant chaque réponse ne l'est pas.

Quand en appeler un :
- Dès qu'une réponse exacte en dépend — actualité, chiffres, faits vérifiables, tout ce qui a pu
  changer depuis ton entraînement. Ne devine pas ce qu'un outil peut établir.
- N'annonce pas que tu vas chercher : appelle l'outil. L'utilisateur voit le résultat arriver.
- Un outil peut échouer ou ne rien trouver. Dis-le tel quel ; ne comble jamais un échec par une
  réponse inventée.
- Fonde ta réponse sur ce que l'outil a réellement rendu, et cite les sources qu'il te donne.
  N'invente jamais une URL, un titre ou une date qui ne vient pas d'un résultat.

Outils disponibles :"""


def construire(outils: Sequence[DescriptionOutil]) -> str:
    """Texte du socle, fonction des outils réellement branchés à cet instant.

    Fonction pure : elle décrit ce qu'on lui donne. Un outil déclaré ici mais absent du registre
    ferait exactement le mensonge que ce fichier combat.
    """
    if not outils:
        return _SANS_OUTIL
    lignes = [f"- {outil.nom} : {outil.description}" for outil in outils]
    return "\n".join([_AVEC_OUTILS, *lignes])


def composer(socle: str, prompt_conversation: str) -> str:
    """Assemble socle et prompt de conversation, dans cet ordre, sans jamais perdre l'un des deux."""
    personnel = prompt_conversation.strip()
    if not personnel:
        return socle
    return f"{socle}\n\n---\n\n{personnel}"
