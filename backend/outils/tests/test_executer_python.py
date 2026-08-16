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
from backend.outils import executer_python, fichiers_bac
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


def test_executer_lance_un_fichier_du_bac(conversation: ResumeConversation, racine_bac: Path) -> None:
    """Le maillon qui referme la boucle écrire → lancer → corriger, sans réémettre le programme."""
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)
    asyncio.run(
        fichiers_bac.OUTIL_ECRIRE.executer(
            {"chemin": "app.py", "contenu": "print('lancé depuis le fichier')\n"}, contexte
        )
    )

    texte = asyncio.run(executer_python.executer({"fichier": "app.py"}, contexte))

    assert "lancé depuis le fichier" in texte
    assert "Code de retour : 0" in texte


def test_executer_un_fichier_execute_le_garde_main(conversation: ResumeConversation, racine_bac: Path) -> None:
    """Un script ordinaire met son travail sous `if __name__ == "__main__":`.

    Sans `run_name='__main__'`, lancer un tel fichier ne produirait rien de visible — ce qui
    ressemble à une panne bien plus qu'à un choix.
    """
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)
    programme = "def principal():\n    print('travail fait')\n\nif __name__ == '__main__':\n    principal()\n"
    asyncio.run(fichiers_bac.OUTIL_ECRIRE.executer({"chemin": "app.py", "contenu": programme}, contexte))

    texte = asyncio.run(executer_python.executer({"fichier": "app.py"}, contexte))

    assert "travail fait" in texte


def test_executer_un_fichier_absent_oriente_vers_l_ecriture(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(executer_python.executer({"fichier": "absent.py"}, contexte))

    assert "Échec" in texte
    assert "ecrire_fichier" in texte


def test_executer_refuse_un_fichier_hors_du_bac(conversation: ResumeConversation, racine_bac: Path) -> None:
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    texte = asyncio.run(executer_python.executer({"fichier": "../../etc/passwd"}, contexte))

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
