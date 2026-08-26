"""Outil `creer_artefact` — le modèle produit quelque chose qui se regarde, et le montre.

DISTINCT DE `presenter_fichier`, et la distinction est le cœur du sujet : celui-ci CRÉE, l'autre
DÉSIGNE un fichier qui existe déjà. Confondre les deux obligerait le modèle à écrire un fichier
puis à le présenter en deux appels, là où il veut faire un geste : « voici la page que je viens
d'écrire ».

VERSIONS. Un artefact est corrigé plus qu'il n'est créé — le modèle produit une page, l'utilisateur
demande un changement, une deuxième version arrive. Le numéro est attribué ICI, par le backend, et
jamais par le modèle : un modèle qui compte lui-même ses versions se trompe dès qu'il perd le fil de
la conversation, et deux versions porteraient le même numéro.

Il n'existe pourtant AUCUNE table d'artefacts, et c'est délibéré. Le numéro se dérive du magasin de
fichiers, qui persiste déjà : les fichiers d'un même artefact portent un nom en `<id>-vN.<ext>`, et
la version suivante est simplement la plus haute plus un. Une table de plus serait un second état à
tenir cohérent avec le premier — et c'est toujours la copie qui diverge.

Le résultat rendu au modèle est un JSON compact que le frontend reconnaît
(`frontend/src/chat/artefacts/detection.ts`), au même titre que celui de `presenter_fichier`. Le
contenu, lui, ne traverse pas ce résultat : il est servi par la route fichiers existante.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from loguru import logger

from backend.fichiers import (
    FichierTropVolumineux,
    QuotaConversationDepasse,
    TypeMimeRefuse,
    deposer_fichier,
    lister_fichiers,
)
from backend.outils.contrat import ContexteExecution, DescriptionOutil, EchecOutil, Outil

NOM = "creer_artefact"

# Types rendus par le frontend. Un type hors liste n'est PAS refusé : il est rendu en texte brut,
# ce qui vaut mieux qu'un appel perdu pour un mot mal choisi. La liste sert à guider le modèle, pas
# à l'arrêter.
TYPES = ("html", "markdown", "code", "svg", "mermaid")

_EXTENSIONS = {"html": "html", "markdown": "md", "code": "txt", "svg": "svg", "mermaid": "mmd"}
_MIMES = {"html": "text/html", "markdown": "text/markdown", "code": "text/plain",
          "svg": "image/svg+xml", "mermaid": "text/plain"}

# L'identifiant d'artefact vient du MODÈLE : c'est donc une entrée non fiable, et il finit dans un
# nom de fichier. Réduit à un jeu de caractères sûr avant tout usage — un `../` y passerait sinon.
_CARACTERES_SURS = re.compile(r"[^a-z0-9-]+")
LONGUEUR_ID_MAX = 48
# Rendu DANS le résultat de l'outil, et non seulement dans sa description.
#
# Mesuré le 2026-08-26 : à « corrige la landing page », le modèle a rappelé l'outil SANS
# `artefact_id`. L'identifiant fut donc redérivé du titre — qui avait bougé d'un mot — et un SECOND
# artefact est né au lieu d'une v2. L'utilisateur s'est retrouvé avec deux pages concurrentes.
#
# La description de l'outil le disait déjà, mais elle est lue une fois, loin en amont, au milieu de
# dix autres. Le résultat, lui, est sous les yeux du modèle au moment exact où il décide de la
# suite : c'est là que la consigne a une chance d'être suivie.
_CONSIGNE_VERSION = (
    "To publish a corrected version of THIS artefact, call `creer_artefact` again with "
    "artefact_id=\"{id}\" and the full new content. Omitting it creates a SEPARATE artefact "
    "instead of a new version."
)

_MOTIF_VERSION = re.compile(r"^(?P<id>.+)-v(?P<version>\d+)\.[^.]+$")

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titre": {
            "type": "string",
            "description": "Short human title, shown on the card and above the artefact. Required.",
        },
        "type": {
            "type": "string",
            "enum": list(TYPES),
            "description": (
                "What the content IS, which decides how it is displayed: `html` renders in a "
                "sandboxed frame, `svg` renders as an image, `markdown` as formatted text, "
                "`mermaid` as a diagram, `code` as highlighted source. Required."
            ),
        },
        "contenu": {
            "type": "string",
            "description": (
                "The full content, inline in this call, however long it is. There is no second "
                "call to complete it later."
            ),
        },
        "langage": {
            "type": "string",
            "description": "For `code` only: the language, for highlighting — `python`, `rust`…",
        },
        "artefact_id": {
            "type": "string",
            "description": (
                "Give this ONLY to publish a NEW VERSION of an artefact you already created: "
                "reuse the exact `artefact_id` it returned. Omit it for a new artefact — an "
                "identifier will be assigned. Never invent one."
            ),
        },
    },
    "required": ["titre", "type", "contenu"],
}

DESCRIPTION = DescriptionOutil(
    nom=NOM,
    description=(
        "Creates a document the user can look at and interact with, shown beside the conversation: "
        "a web page, a diagram, a document, a piece of code. Use it whenever the answer IS an "
        "object rather than a paragraph — a page you wrote, a chart, a file to read. To correct it "
        "afterwards, call this again with the same `artefact_id` and the full new content: that "
        "publishes a new version, and the user can switch between them."
    ),
    parametres=_SCHEMA,
    alias={
        **{a: "contenu" for a in ("content", "corps", "texte", "source", "body", "code")},
        **{a: "titre" for a in ("title", "nom", "name")},
        **{a: "type" for a in ("kind", "format", "type_artefact")},
        **{a: "artefact_id" for a in ("id", "identifiant", "artefact", "artifact_id")},
    },
)


def _identifiant(titre: str, fourni: str) -> str:
    """Identifiant d'artefact : celui fourni s'il est sain, sinon dérivé du titre.

    Jamais utilisé tel quel : c'est une chaîne écrite par un modèle, et elle devient un nom de
    fichier. La normalisation retire les accents, tout ce qui n'est pas alphanumérique, et borne la
    longueur — un `../` ou un nom de 400 caractères ne survit pas à ce passage.
    """
    brut = (fourni or titre).strip().lower()
    sans_accent = unicodedata.normalize("NFKD", brut).encode("ascii", "ignore").decode()
    entier = _CARACTERES_SURS.sub("-", sans_accent).strip("-")
    propre = entier[:LONGUEUR_ID_MAX].strip("-")
    if not fourni and len(entier) > LONGUEUR_ID_MAX:
        # Un identifiant dérivé d'un titre TRONQUÉ est instable : deux titres qui ne diffèrent
        # qu'après le 48e caractère donnent le même identifiant, et deux titres qui diffèrent avant
        # en donnent deux — c'est ainsi qu'un artefact s'est dédoublé le 2026-08-26.
        logger.info("Identifiant d'artefact dérivé d'un titre tronqué ({} → {}) : "
                    "le modèle devrait renvoyer `artefact_id` pour versionner.", entier, propre)
    return propre or "artefact"


def _prochaine_version(conversation_id: str, artefact_id: str) -> int:
    """Version suivante, dérivée des fichiers déjà déposés. 1 quand l'artefact est nouveau.

    Lue depuis le magasin plutôt que depuis un compteur : le magasin est la seule source qui
    survive à un redémarrage, et un compteur en mémoire recommencerait à 1 en écrasant l'historique.
    """
    versions = [0]
    for fichier in lister_fichiers(conversation_id):
        trouve = _MOTIF_VERSION.match(fichier.nom_affiche)
        if trouve is not None and trouve.group("id") == artefact_id:
            versions.append(int(trouve.group("version")))
    return max(versions) + 1


def _valider(arguments: dict[str, Any]) -> tuple[str, str, str, str]:
    """Titre, type, contenu et langage validés — ou un refus qui dit la forme attendue."""
    titre = str(arguments.get("titre", "")).strip()
    contenu = str(arguments.get("contenu", ""))
    type_ = str(arguments.get("type", "")).strip().lower()
    if not titre or not contenu.strip():
        raise EchecOutil(
            "An artefact needs both `titre` and `contenu`, complete in this single call. "
            'Example: {"titre": "Page d\'accueil", "type": "html", "contenu": "<!doctype html>…"}')
    if not type_:
        raise EchecOutil(f"Missing `type`. Expected one of: {', '.join(TYPES)}.")
    return titre, type_, contenu, str(arguments.get("langage", "")).strip()


async def executer(arguments: dict[str, Any], contexte: ContexteExecution) -> str:
    """Dépose le contenu comme fichier de la conversation et rend la carte que le frontend lit."""
    titre, type_, contenu, langage = _valider(arguments)
    artefact_id = _identifiant(titre, str(arguments.get("artefact_id", "")))
    version = _prochaine_version(contexte.conversation_id, artefact_id)
    octets = contenu.encode("utf-8")
    nom = f"{artefact_id}-v{version}.{_EXTENSIONS.get(type_, 'txt')}"
    try:
        fichier = deposer_fichier(
            contexte.conversation_id, nom_fourni=nom,
            type_mime_declare=_MIMES.get(type_, "text/plain"),
            octets=octets, origine="modele")
    except (FichierTropVolumineux, QuotaConversationDepasse, TypeMimeRefuse) as exc:
        logger.warning("Artefact {} refusé par le magasin : {}", nom, exc)
        raise EchecOutil(f"The artefact could not be stored: {exc}") from exc
    logger.info("Artefact {} v{} déposé ({} octets, type {})", artefact_id, version, len(octets), type_)
    return json.dumps(
        {"artefact_id": artefact_id, "version": version, "titre": titre, "type": type_,
         "langage": langage or None, "fichier_id": fichier.id, "taille_octets": len(octets),
         "pour_corriger": _CONSIGNE_VERSION.format(id=artefact_id)},
        ensure_ascii=False)


OUTIL = Outil(description=DESCRIPTION, executer=executer)

__all__ = ["OUTIL", "TYPES"]
