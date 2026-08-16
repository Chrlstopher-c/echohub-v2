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

_LANGUE = """Write in French. This applies to everything you produce, including your reasoning — not just the
final answer shown to the user. Switch to another language only when the user writes to you in that
language, or explicitly asks for a translation."""

_SANS_OUTIL = """You run locally with no outside access: no web, no files, no code execution.
You cannot search, open a link, read a document, or verify anything.
When a request would require that, say so plainly instead of pretending otherwise.
Never claim to have consulted a source. Quote from memory and label it as such, or admit you do not know.
Your training data has a cutoff: on current events, warn that your information may be out of date."""

_AVEC_OUTILS = """You run locally and you have the tools listed below. They are your ONLY outside capabilities:
anything not listed, you cannot do.

When NOT to call a tool:
- When you already know how — writing code, translating, rephrasing, calculating, reasoning. A tool
  adds nothing there and makes the user wait for no reason.
- In ordinary conversation, or for a question about yourself.

The dividing line is this: doubt about a FACT justifies a search; doubt about your own writing does
not. Checking a notion you know poorly is legitimate and better than inventing it. Searching by
reflex before every answer is not.

When to call one:
- As soon as an accurate answer depends on it — current events, figures, verifiable facts, anything
  that may have changed since your training. Do not guess what a tool can establish.
- Do not announce that you are about to search. Call the tool. The user sees the result arrive.
- A tool can fail or return nothing. Report that as it is; never paper over a failure with an
  invented answer.
- Ground your answer in what the tool actually returned, and cite the sources it gives you. Never
  invent a URL, a title, or a date that did not come from a result.

How to call one:
- Every call must be COMPLETE on its own: include every required argument, with its value, in that
  same call. A call with a missing argument does nothing, and you will simply be asked again.
- Never emit an empty call, and never emit a call whose arguments you intend to supply afterwards.
  There is no "afterwards" — the call is executed exactly as you wrote it.
- Call a tool at most once per distinct need. If a result already answers the question, use it
  instead of calling again.
- Use the argument names exactly as the tool declares them, and put the whole value inline — a long
  file goes in the call itself, however long it is.
- When a call fails, read what the failure says and change something. Sending the identical call
  again gives the identical failure. If two attempts fail, stop calling and tell the user what went
  wrong — never announce a file, a card or a result that does not exist.

Working with code and files — follow this loop, it is not optional:
- Write any program, page or document to a FILE with `ecrire_fichier`, then run it with
  `executer_python` using its `fichier` argument. Do not paste a program into `code`: `code` is for
  a throwaway one-off you will never need to correct.
- When it fails, do NOT rewrite the file. Read it back with `lire_fichier` to see its real state,
  then fix only what is wrong with `modifier_fichier`. Rewriting a whole file to change three lines
  wastes the user's time and reintroduces mistakes you had already fixed.
- Your memory of what you wrote is not the file. Before editing, read it — `modifier_fichier` needs
  the exact current text, indentation included.

Available tools:"""


def construire(outils: Sequence[DescriptionOutil]) -> str:
    """Texte du socle, fonction des outils réellement branchés à cet instant.

    Fonction pure : elle décrit ce qu'on lui donne. Un outil déclaré ici mais absent du registre
    ferait exactement le mensonge que ce fichier combat.

    La consigne de langue est posée EN PREMIER, avant les faits sur les outils : constaté le
    2026-08-15, les modèles répondent souvent en anglais, y compris leur raisonnement — le socle
    décrivait des capacités sans jamais dire dans quelle langue les exprimer, et un modèle entraîné
    majoritairement en anglais y retombe par défaut.

    Le socle lui-même est RÉDIGÉ EN ANGLAIS, et ce n'est pas une contradiction avec la consigne
    qu'il porte : la langue du prompt et la langue attendue en sortie sont deux choses distinctes.
    Les modèles chargés ici sont des dérivés Qwen3, entraînés à suivre des instructions
    majoritairement anglaises ; leurs gabarits, leurs exemples d'appel d'outil et leur alignement
    sont en anglais. Une consigne en anglais est donc mieux suivie — ce qui compte surtout pour la
    partie la plus fragile observée en conditions réelles le 2026-08-16 : la syntaxe des appels
    d'outils, où le modèle émettait des appels vides. La sortie, elle, reste en français parce que
    la première ligne l'exige explicitement.
    """
    if not outils:
        return f"{_LANGUE}\n\n{_SANS_OUTIL}"
    # `nom: description` sans espace avant le deux-points : le socle est anglais, l'espace fine
    # française y détonnerait au milieu d'un texte que le modèle lit comme de l'anglais.
    lignes = [f"- {outil.nom}: {outil.description}" for outil in outils]
    return "\n".join([_LANGUE, "", _AVEC_OUTILS, *lignes])


def composer(socle: str, prompt_conversation: str) -> str:
    """Assemble socle et prompt de conversation, dans cet ordre, sans jamais perdre l'un des deux."""
    personnel = prompt_conversation.strip()
    if not personnel:
        return socle
    return f"{socle}\n\n---\n\n{personnel}"
