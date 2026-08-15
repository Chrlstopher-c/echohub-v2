"""Preuve d'assemblage (plan d'exécution, 2.7) : `presenter_fichier` est atteignable depuis le
REGISTRE réel — la même entrée que `backend/inference/__init__.py::_executer_appels` appelle
réellement dans `MoteurChat._flux`, pas une copie du test.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.chat.modeles import ResumeConversation
from backend.fichiers import deposer_fichier
from backend.outils import registre
from backend.outils.contrat import ContexteExecution


def test_le_registre_declare_presenter_fichier() -> None:
    noms = {outil.nom for outil in registre.disponibles()}
    assert "presenter_fichier" in noms


def test_le_registre_execute_presenter_fichier(conversation: ResumeConversation, racine_bac: Path) -> None:
    fichier = deposer_fichier(
        conversation.id,
        nom_fourni="script.py",
        type_mime_declare="text/x-python",
        octets=b"print('bonjour')",
        origine="modele",
    )
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    resultat = asyncio.run(registre.executer("presenter_fichier", {"fichier_id": fichier.id}, contexte))

    assert resultat.succes
    donnees = json.loads(resultat.texte)
    assert donnees["fichier_id"] == fichier.id
    assert donnees["nom_affiche"] == "script.py"
