"""Preuve qu'un appel d'outil au JSON incomplet est réparé plutôt que perdu.

Charge RÉELLE relevée le 2026-08-16 : le gabarit ouvre `{{"name": …, "arguments": {…` — trois
accolades ouvrantes — et n'en referme que deux. La réduction des accolades doublées ne suffisait
donc pas : le JSON restait déséquilibré et l'appel était perdu ENTIER. Le modèle s'arrêtait alors
sur un `<tool_call>` que personne n'exécutait, et l'utilisateur voyait une réponse morte.

Même forme quand la fenêtre de contexte coupe la génération en plein argument : le début de l'appel
est parfaitement lisible, seule la fin manque. Refuser tout un appel — donc tout un tour de travail
du modèle — pour des accolades absentes est un choix du harnais, pas une fatalité.

Ce qui est réparé : ce que le modèle a OUVERT et pas refermé. Rien n'est inventé — un appel sans nom
reste refusé.
"""

from __future__ import annotations

from backend.inference.engines_adapters.adaptateur_llama_cpp import (
    _appels_dans_le_texte,
    _charger_json_tolerant,
    _fermetures_manquantes,
)


def _arguments(texte: str) -> dict[str, object]:
    appels = _appels_dans_le_texte(texte)
    assert len(appels) == 1, f"un appel attendu, {len(appels)} trouvé(s)"
    return dict(appels[0]["function"]["arguments"])


def test_le_cas_reel_a_trois_accolades_ouvrantes_est_lu() -> None:
    texte = (
        '<tool_call>{{"name": "ecrire_fichier", "arguments": '
        '{"chemin": "page.txt", "contenu": "bonjour"}}</tool_call>'
    )
    assert _arguments(texte) == {"chemin": "page.txt", "contenu": "bonjour"}


def test_un_appel_coupe_net_par_la_fenetre_est_lu() -> None:
    """Le début est exploitable : le jeter obligerait le modèle à tout réémettre."""
    texte = '<tool_call>{"name": "ecrire_fichier", "arguments": {"chemin": "a.py", "contenu": "print(1)'
    assert _arguments(texte) == {"chemin": "a.py", "contenu": "print(1)"}


def test_une_accolade_dans_une_chaine_ne_fausse_pas_le_comptage() -> None:
    """On écrit du code avec ces outils : une accolade dans le contenu est le cas NORMAL."""
    texte = (
        '<tool_call>{"name": "ecrire_fichier", "arguments": '
        '{"chemin": "a.css", "contenu": "body { color: red; }"}}</tool_call>'
    )
    assert _arguments(texte)["contenu"] == "body { color: red; }"


def test_un_guillemet_echappe_ne_fausse_pas_le_comptage() -> None:
    texte = '<tool_call>{"name": "ecrire_fichier", "arguments": {"chemin": "a.py", "contenu": "dit \\"salut\\"'
    assert _arguments(texte)["contenu"] == 'dit "salut"'


def test_un_appel_bien_forme_est_lu_sans_reparation() -> None:
    """Garde-fou : la tolérance ne doit rien changer au cas normal."""
    texte = '<tool_call>{"name": "recherche_web", "arguments": {"requete": "météo"}}</tool_call>'
    assert _arguments(texte) == {"requete": "météo"}


def test_les_fermetures_manquantes_respectent_l_ordre_d_ouverture() -> None:
    assert _fermetures_manquantes('{"a": [1, 2') == "]}"
    assert _fermetures_manquantes('{"a": "b') == '"}'
    assert _fermetures_manquantes('{"a": "b"}') == ""


def test_un_texte_vraiment_illisible_reste_refuse() -> None:
    """La réparation referme ce qui est ouvert ; elle n'invente pas un appel qui n'existe pas."""
    assert _charger_json_tolerant("ceci n'est pas du JSON") is None
