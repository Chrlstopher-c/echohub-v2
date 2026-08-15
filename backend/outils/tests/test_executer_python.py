"""Preuves de l'outil `executer_python` — la fonction que le registre appelle réellement.

`executer()` est appelée directement ici, la même fonction que celle enregistrée dans
`registre._OUTILS` (voir `test_registre_executer_python.py` pour la preuve depuis le registre lui-
même, l'entrée réelle utilisée par `MoteurChat`).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from backend.chat.modeles import ResumeConversation
from backend.fichiers import chemin_disque, lire_fichier
from backend.outils import executer_python
from backend.outils.contrat import ContexteExecution

_MOTIF_ID_FICHIER = re.compile(r"\(id ([0-9a-f-]{36})\)")


def test_executer_rend_la_sortie_standard(conversation: ResumeConversation, racine_bac: Path) -> None:
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(executer_python.executer({"code": "print('bonjour depuis le bac')"}, contexte))

    assert "bonjour depuis le bac" in texte
    assert "Code de retour : 0" in texte


def test_executer_signale_lechec_dun_code_qui_leve(conversation: ResumeConversation, racine_bac: Path) -> None:
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(executer_python.executer({"code": "raise ValueError('boom')"}, contexte))

    assert "Code de retour : 1" in texte
    assert "ValueError" in texte
    assert "boom" in texte


def test_executer_refuse_labsence_de_code(conversation: ResumeConversation, racine_bac: Path) -> None:
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(executer_python.executer({}, contexte))

    assert "Échec" in texte


def test_executer_enregistre_le_fichier_produit_dans_le_magasin(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    """Preuve d'assemblage locale : de l'appel réel de l'outil jusqu'au fichier retrouvé dans le
    magasin, via la même route publique (`lire_fichier`, `chemin_disque`) que la route HTTP."""
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)
    code = "open('sortie.csv', 'w').write('a,b\\n1,2\\n')"

    texte = asyncio.run(executer_python.executer({"code": code}, contexte))

    assert "sortie.csv" in texte
    correspondance = _MOTIF_ID_FICHIER.search(texte)
    assert correspondance is not None, f"aucun identifiant de fichier dans le résultat : {texte!r}"

    fichier = lire_fichier(correspondance.group(1))
    assert fichier.origine == "modele"
    assert fichier.nom_affiche == "sortie.csv"
    assert fichier.conversation_id == conversation.id
    assert chemin_disque(fichier).read_text() == "a,b\n1,2\n"
