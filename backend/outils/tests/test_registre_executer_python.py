"""Preuve d'assemblage (plan d'exécution, 2.7) : `executer_python` est atteignable depuis le
REGISTRE réel, l'entrée que `backend/inference/__init__.py::_resoudre_outils` appelle réellement —
pas une copie du test, le même `registre.executer` que `test_contexte_execution_outil.py` exerce
depuis `MoteurChat`.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from backend.chat.modeles import ResumeConversation
from backend.fichiers import chemin_disque, lire_fichier
from backend.outils import registre
from backend.outils.contrat import ContexteExecution


def test_le_registre_declare_executer_python() -> None:
    noms = {outil.nom for outil in registre.disponibles()}
    assert "executer_python" in noms


def test_le_registre_execute_et_le_fichier_produit_atteint_le_magasin(
    conversation: ResumeConversation, racine_bac: Path
) -> None:
    contexte = ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)

    resultat = asyncio.run(
        registre.executer("executer_python", {"code": "open('via_registre.txt', 'w').write('ok')"}, contexte)
    )

    assert resultat.succes
    correspondance = re.search(r"\(id ([0-9a-f-]{36})\)", resultat.texte)
    assert correspondance is not None

    fichier = lire_fichier(correspondance.group(1))
    assert fichier.origine == "modele"
    assert fichier.nom_affiche == "via_registre.txt"
    assert chemin_disque(fichier).read_text() == "ok"
