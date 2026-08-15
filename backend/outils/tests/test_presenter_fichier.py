"""Preuves de l'outil `presenter_fichier` — la fonction que le registre appelle réellement.

`executer()` est appelée directement ici, la même fonction que celle enregistrée dans
`registre._OUTILS` (voir `test_registre_presenter_fichier.py` pour la preuve depuis le registre
lui-même).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.chat.depot import creer_conversation
from backend.chat.modeles import ReglagesConversation, ResumeConversation
from backend.fichiers import deposer_fichier
from backend.outils import presenter_fichier
from backend.outils.contrat import ContexteExecution


def _deposer(conversation_id: str) -> str:
    fichier = deposer_fichier(
        conversation_id,
        nom_fourni="rapport.html",
        type_mime_declare="text/html",
        octets=b"<html><body>ok</body></html>",
        origine="modele",
    )
    return fichier.id


def test_presenter_rend_une_reference_json_du_fichier(conversation: ResumeConversation, racine_bac: Path) -> None:
    fichier_id = _deposer(conversation.id)
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(presenter_fichier.executer({"fichier_id": fichier_id}, contexte))

    donnees = json.loads(texte)
    assert donnees["fichier_id"] == fichier_id
    assert donnees["nom_affiche"] == "rapport.html"
    assert donnees["type_mime"] == "text/html"
    assert donnees["taille_octets"] > 0
    assert donnees["origine"] == "modele"


def test_presenter_refuse_un_identifiant_inconnu(conversation: ResumeConversation, racine_bac: Path) -> None:
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(presenter_fichier.executer({"fichier_id": "inexistant"}, contexte))

    assert "Échec" in texte


def test_presenter_refuse_labsence_didentifiant(conversation: ResumeConversation, racine_bac: Path) -> None:
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(presenter_fichier.executer({}, contexte))

    assert "Échec" in texte


def test_presenter_refuse_un_fichier_dune_autre_conversation(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    """Validation dans les deux sens : un identifiant réel, mais d'une autre conversation, doit
    être refusé comme s'il n'existait pas — jamais rendu visible."""
    autre = creer_conversation("Autre conversation", None, ReglagesConversation())
    fichier_id = _deposer(autre.id)
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(presenter_fichier.executer({"fichier_id": fichier_id}, contexte))

    # L'identifiant redonné n'est pas une fuite : c'est celui que l'appelant a lui-même fourni.
    # Ce qui doit rester absent, c'est le CONTENU du fichier d'autrui — son nom, son type MIME.
    assert "Échec" in texte
    assert "rapport.html" not in texte
    assert "text/html" not in texte
