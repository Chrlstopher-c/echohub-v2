"""Surface fichier du bac : écrire, lire, modifier — sans repasser par du code Python.

Raison d'être, constatée le 2026-08-16 et non supposée. Le seul moyen de produire un fichier était
`executer_python` : le modèle devait donc emballer son contenu dans du source Python, ce qui
l'obligeait à échapper deux fois guillemets et retours à la ligne. Le résultat observé était un
`open("hello.py","w").write("...\\n...\\\"...")` illisible — et surtout, à la MOINDRE erreur, le
modèle réécrivait le fichier ENTIER depuis zéro, parce qu'il n'avait aucun moyen d'en toucher une
partie. Sur une page HTML de 3,6 Kio, chaque correction de virgule coûtait une réémission complète.

Les trois outils forment la boucle de travail attendue :

    ecrire_fichier   -> pose le fichier, contenu brut, aucun échappement
    executer_python  -> le lance (paramètre `fichier`)
    lire_fichier     -> relit l'état RÉEL avant de corriger, plutôt que de se fier à sa mémoire
    modifier_fichier -> remplace un fragment exact, le reste du fichier n'est jamais retouché

`modifier_fichier` exige que le fragment cherché apparaisse EXACTEMENT une fois. Zéro occurrence :
le modèle s'est trompé de texte, il doit relire. Plusieurs : la modification serait ambiguë, et
choisir à sa place produirait une édition au mauvais endroit — silencieuse, donc pire qu'un refus.

Chaque écriture est redéposée dans le magasin de `backend.fichiers`. Sans cela, `presenter_fichier`
montrerait la version d'avant l'édition : le dépôt sert les octets qu'il a enregistrés, pas ceux du
bac. Le magasin garde donc plusieurs versions du même nom, et `resoudre_reference` rend la plus
récente — c'est exactement ce que le modèle vient d'écrire.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from loguru import logger

from backend.core import EchoHubError
from backend.fichiers import deposer_fichier
from backend.outils.bac_a_sable import CheminHorsBac, adopter_par_le_bac, preparer_bac, resoudre_dans_bac
from backend.outils.contrat import ContexteExecution, DescriptionOutil, Outil

# Un fichier relu repart dans le contexte du modèle. Au-delà, la fenêtre se remplit d'un seul
# fichier et l'historique de la conversation disparaît. `ResultatOutil.tronque()` s'applique de
# toute façon en aval ; cette borne évite seulement de construire un texte énorme avant d'y arriver.
LONGUEUR_LECTURE_MAX = 6_000

_CHEMIN = {
    "type": "string",
    "description": (
        "Path of the file inside this conversation's sandbox, relative — `app.py`, `src/page.html`. "
        "Required: a call without it does nothing. Absolute paths and paths leaving the sandbox are "
        "refused."
    ),
}


def _enregistrer(contexte: ContexteExecution, chemin_relatif: str, cible: Path) -> str:
    """Redépose le fichier dans le magasin et rend la mention à afficher au modèle.

    Un échec de dépôt (quota, type MIME hors liste blanche) n'annule pas l'écriture : le fichier
    existe bel et bien dans le bac et le code confiné peut s'en servir. On le dit, sans transformer
    un refus d'affichage en échec d'écriture.
    """
    type_mime, _ = mimetypes.guess_type(chemin_relatif)
    try:
        fichier = deposer_fichier(
            contexte.conversation_id,
            nom_fourni=chemin_relatif,
            type_mime_declare=type_mime,
            octets=cible.read_bytes(),
            origine="modele",
        )
    except EchoHubError as exc:
        logger.warning("Fichier {} écrit mais non déposé dans le magasin : {}", chemin_relatif, exc)
        return "Non présentable dans la conversation (refusé par le magasin), mais bien présent dans le bac."
    return f"Déposé dans la conversation sous « {fichier.nom_affiche} » (id {fichier.id})."


def _preparer_cible(contexte: ContexteExecution, chemin_demande: str) -> Path:
    """Résout le chemin dans le bac et crée les dossiers parents. Lève `CheminHorsBac` si hors bac."""
    preparer_bac(contexte.racine_bac)
    cible = resoudre_dans_bac(contexte.racine_bac, chemin_demande)
    cible.parent.mkdir(parents=True, exist_ok=True)
    return cible


# --- ecrire_fichier ----------------------------------------------------------------------------

DESCRIPTION_ECRIRE = DescriptionOutil(
    nom="ecrire_fichier",
    description=(
        "Writes a file into this conversation's sandbox, creating it or overwriting it entirely. "
        "Pass the content RAW — no Python quoting, no escaping. This is how you create any file you "
        "intend to run, show, or edit afterwards. To change part of an existing file, use "
        "`modifier_fichier` instead: never rewrite a whole file to fix a few lines."
    ),
    parametres={
        "type": "object",
        "properties": {
            "chemin": _CHEMIN,
            "contenu": {
                "type": "string",
                "description": "The full text to write. Required: a call without it does nothing.",
            },
        },
        "required": ["chemin", "contenu"],
    },
)


async def _ecrire(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
    chemin_demande = str(arguments.get("chemin", "")).strip()
    contenu = arguments.get("contenu")
    if contenu is None:
        return "Échec : aucun « contenu » fourni. Rappeler l'outil avec le texte complet du fichier."
    try:
        cible = _preparer_cible(contexte, chemin_demande)
    except CheminHorsBac as exc:
        return f"Échec : {exc}"
    octets = str(contenu).encode("utf-8")
    cible.write_bytes(octets)
    adopter_par_le_bac(cible)
    mention = _enregistrer(contexte, chemin_demande, cible)
    lignes = str(contenu).count("\n") + 1
    return f"Écrit « {chemin_demande} » ({len(octets)} octets, {lignes} lignes). {mention}"


# --- lire_fichier ------------------------------------------------------------------------------

DESCRIPTION_LIRE = DescriptionOutil(
    nom="lire_fichier",
    description=(
        "Reads back a file from this conversation's sandbox, exactly as it stands on disk. Use it "
        "before editing: `modifier_fichier` needs the exact current text, and your memory of what "
        "you wrote is not the file. Also use it after an error, to see the real state rather than "
        "guessing."
    ),
    parametres={"type": "object", "properties": {"chemin": _CHEMIN}, "required": ["chemin"]},
)


async def _lire(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
    chemin_demande = str(arguments.get("chemin", "")).strip()
    try:
        cible = resoudre_dans_bac(contexte.racine_bac, chemin_demande)
    except CheminHorsBac as exc:
        return f"Échec : {exc}"
    if not cible.is_file():
        return f"Échec : « {chemin_demande} » n'existe pas dans le bac de cette conversation."
    try:
        texte = cible.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"Échec : « {chemin_demande} » illisible en texte ({exc})."
    if len(texte) > LONGUEUR_LECTURE_MAX:
        coupe = texte[:LONGUEUR_LECTURE_MAX]
        return f"{coupe}\n\n[lecture tronquée à {LONGUEUR_LECTURE_MAX} caractères sur {len(texte)}]"
    return texte


# --- modifier_fichier --------------------------------------------------------------------------

DESCRIPTION_MODIFIER = DescriptionOutil(
    nom="modifier_fichier",
    description=(
        "Replaces one exact fragment inside an existing sandbox file, leaving everything else "
        "untouched. This is the tool to fix an error: change the few lines that are wrong instead "
        "of rewriting the whole file. The fragment must appear EXACTLY once — read the file first "
        "with `lire_fichier` and copy the text verbatim, including its indentation."
    ),
    parametres={
        "type": "object",
        "properties": {
            "chemin": _CHEMIN,
            "ancien": {
                "type": "string",
                "description": (
                    "The exact text to replace, copied verbatim from the file, including "
                    "indentation and line breaks. Must occur exactly once. Required."
                ),
            },
            "nouveau": {
                "type": "string",
                "description": "The text to put in its place. Required — use an empty string to delete.",
            },
        },
        "required": ["chemin", "ancien", "nouveau"],
    },
)


def _verdict_occurrences(nombre: int, ancien: str) -> str | None:
    """Message d'échec quand le fragment n'est pas trouvable exactement une fois, sinon `None`."""
    if nombre == 1:
        return None
    extrait = ancien[:80].replace("\n", "⏎")
    if nombre == 0:
        return (
            f"Échec : le fragment « {extrait} » n'apparaît pas dans le fichier. "
            "Relire le fichier avec `lire_fichier` et recopier le texte exact."
        )
    return (
        f"Échec : le fragment « {extrait} » apparaît {nombre} fois. "
        "Choisir dans quelle occurrence intervenir est impossible — allonger le fragment pour "
        "qu'il devienne unique, en incluant les lignes qui l'entourent."
    )


async def _modifier(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
    chemin_demande = str(arguments.get("chemin", "")).strip()
    ancien = arguments.get("ancien")
    nouveau = arguments.get("nouveau")
    if not ancien:
        return "Échec : aucun « ancien » fourni. Rappeler l'outil avec le texte exact à remplacer."
    if nouveau is None:
        return "Échec : aucun « nouveau » fourni. Utiliser une chaîne vide pour supprimer le fragment."
    try:
        cible = resoudre_dans_bac(contexte.racine_bac, chemin_demande)
    except CheminHorsBac as exc:
        return f"Échec : {exc}"
    if not cible.is_file():
        return f"Échec : « {chemin_demande} » n'existe pas. Le créer d'abord avec `ecrire_fichier`."
    try:
        texte = cible.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"Échec : « {chemin_demande} » illisible en texte ({exc})."
    refus = _verdict_occurrences(texte.count(str(ancien)), str(ancien))
    if refus is not None:
        return refus
    cible.write_text(texte.replace(str(ancien), str(nouveau), 1), encoding="utf-8")
    adopter_par_le_bac(cible)
    mention = _enregistrer(contexte, chemin_demande, cible)
    return f"Modifié « {chemin_demande} » : un fragment remplacé, le reste du fichier est intact. {mention}"


OUTIL_ECRIRE = Outil(description=DESCRIPTION_ECRIRE, executer=_ecrire)
OUTIL_LIRE = Outil(description=DESCRIPTION_LIRE, executer=_lire)
OUTIL_MODIFIER = Outil(description=DESCRIPTION_MODIFIER, executer=_modifier)

__all__ = ["OUTIL_ECRIRE", "OUTIL_LIRE", "OUTIL_MODIFIER"]
