"""Preuve de la boucle écrire / lire / modifier, et de la frontière du bac.

Défaut réel du 2026-08-16 : `executer_python` étant le seul moyen de produire un fichier, le modèle
emballait son contenu dans du source Python — doubles échappements illisibles — et, à la moindre
erreur, RÉÉCRIVAIT le fichier entier faute de pouvoir en toucher une partie. Sur une page HTML de
3,6 Kio, corriger une virgule coûtait une réémission complète.

Les tests de chemin ne sont pas décoratifs : le nom du fichier vient du modèle, c'est donc une
entrée non fiable, et l'évasion hors du bac est la seule faute de ce module qui serait grave.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.chat.modeles import ResumeConversation
from backend.outils.contrat import ContexteExecution
from backend.outils.fichiers_bac import OUTIL_ECRIRE, OUTIL_LIRE, OUTIL_MODIFIER


@pytest.fixture
def contexte(conversation: ResumeConversation, racine_bac: Path) -> ContexteExecution:
    return ContexteExecution(conversation_id=conversation.id, racine_bac=racine_bac)


def _executer(outil, arguments: dict, contexte: ContexteExecution) -> str:
    return asyncio.run(outil.executer(arguments, contexte))


def _ecrire(contexte: ContexteExecution, chemin: str, contenu: str) -> str:
    return _executer(OUTIL_ECRIRE, {"chemin": chemin, "contenu": contenu}, contexte)


def test_ecrire_puis_relire_rend_le_contenu_exact(contexte: ContexteExecution) -> None:
    """Le contenu part BRUT : aucun échappement à faire, c'est tout l'intérêt de l'outil."""
    contenu = 'print("Bonjour")\n# accolades {} et "guillemets"\n'
    _ecrire(contexte, "app.py", contenu)
    assert _executer(OUTIL_LIRE, {"chemin": "app.py"}, contexte) == contenu


def test_ecrire_cree_les_dossiers_parents(contexte: ContexteExecution) -> None:
    _ecrire(contexte, "src/pages/index.html", "<h1>Salut</h1>")
    assert _executer(OUTIL_LIRE, {"chemin": "src/pages/index.html"}, contexte) == "<h1>Salut</h1>"


def test_le_fichier_ecrit_est_depose_dans_la_conversation(contexte: ContexteExecution) -> None:
    """Sans dépôt, `presenter_fichier` ne saurait pas montrer ce que le modèle vient d'écrire."""
    assert "Déposé dans la conversation" in _ecrire(contexte, "note.txt", "bonjour")


def test_modifier_ne_touche_que_le_fragment_vise(contexte: ContexteExecution) -> None:
    """Le cœur du sujet : corriger trois lignes ne doit pas réécrire le fichier."""
    _ecrire(contexte, "app.py", "a = 1\nb = 2\nc = 3\n")
    _executer(OUTIL_MODIFIER, {"chemin": "app.py", "ancien": "b = 2", "nouveau": "b = 20"}, contexte)
    assert _executer(OUTIL_LIRE, {"chemin": "app.py"}, contexte) == "a = 1\nb = 20\nc = 3\n"


def test_modifier_avec_un_fragment_absent_refuse_et_dit_quoi_faire(contexte: ContexteExecution) -> None:
    _ecrire(contexte, "app.py", "a = 1\n")
    resultat = _executer(OUTIL_MODIFIER, {"chemin": "app.py", "ancien": "z = 9", "nouveau": "z = 0"}, contexte)
    assert "n'apparaît pas" in resultat
    assert "lire_fichier" in resultat
    assert _executer(OUTIL_LIRE, {"chemin": "app.py"}, contexte) == "a = 1\n", "fichier inchangé après refus"


def test_modifier_avec_un_fragment_ambigu_refuse(contexte: ContexteExecution) -> None:
    """Choisir l'occurrence à la place du modèle produirait une édition silencieuse au mauvais endroit."""
    _ecrire(contexte, "app.py", "x = 1\nx = 1\n")
    resultat = _executer(OUTIL_MODIFIER, {"chemin": "app.py", "ancien": "x = 1", "nouveau": "x = 2"}, contexte)
    assert "2 fois" in resultat
    assert _executer(OUTIL_LIRE, {"chemin": "app.py"}, contexte) == "x = 1\nx = 1\n", "fichier inchangé"


def test_modifier_un_fichier_absent_oriente_vers_l_ecriture(contexte: ContexteExecution) -> None:
    resultat = _executer(OUTIL_MODIFIER, {"chemin": "absent.py", "ancien": "a", "nouveau": "b"}, contexte)
    assert "ecrire_fichier" in resultat


def test_lire_un_fichier_absent_le_dit(contexte: ContexteExecution) -> None:
    assert "n'existe pas" in _executer(OUTIL_LIRE, {"chemin": "absent.py"}, contexte)


@pytest.mark.parametrize("chemin", ["../evade.txt", "../../evade.txt", "sous/../../evade.txt", "/etc/passwd"])
def test_aucune_ecriture_hors_du_bac(contexte: ContexteExecution, chemin: str, tmp_path: Path) -> None:
    """La faute grave de ce module : un chemin du modèle qui sort de son bac."""
    resultat = _ecrire(contexte, chemin, "contenu")
    assert resultat.startswith("Échec"), f"« {chemin} » aurait dû être refusé"
    assert not (contexte.racine_bac.parent / "evade.txt").exists()


@pytest.mark.parametrize("chemin", ["../evade.txt", "/etc/passwd"])
def test_aucune_lecture_hors_du_bac(contexte: ContexteExecution, chemin: str) -> None:
    assert _executer(OUTIL_LIRE, {"chemin": chemin}, contexte).startswith("Échec")


def test_un_lien_symbolique_vers_l_exterieur_est_refuse(contexte: ContexteExecution, tmp_path: Path) -> None:
    """Vérifier le texte du chemin ne suffit pas : la résolution doit suivre les liens."""
    dehors = tmp_path / "dehors.txt"
    dehors.write_text("secret", encoding="utf-8")
    contexte.racine_bac.mkdir(parents=True, exist_ok=True)
    (contexte.racine_bac / "lien.txt").symlink_to(dehors)
    assert _executer(OUTIL_LIRE, {"chemin": "lien.txt"}, contexte).startswith("Échec")


def test_appel_sans_contenu_refuse_sans_ecrire(contexte: ContexteExecution) -> None:
    """L'appel incomplet observé en conditions réelles : il doit échouer proprement, pas créer un vide."""
    assert _executer(OUTIL_ECRIRE, {"chemin": "vide.py"}, contexte).startswith("Échec")
    assert not (contexte.racine_bac / "vide.py").exists()
