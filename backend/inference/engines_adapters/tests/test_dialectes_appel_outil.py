"""Preuve de la lecture des appels d'outils écrits DANS le texte, dans les deux dialectes observés.

Les modèles chargés ici n'utilisent pas tous la même convention, et aucune n'est devinable avant de
l'avoir vue arriver :

- JSON dans `<tool_call>…</tool_call>` — convention Qwen3 générique ;
- balisage `<function=nom><parameter=clé>valeur</parameter></function>` — convention de la famille
  Qwen3-Coder, constatée le 2026-08-15 sur les dérivés chargés ici.

La tolérance aux balises fermantes manquantes est la propriété la plus importante de ce module, et
elle vient d'un défaut mesuré : une quantification basse ou une génération arrêtée net laisse une
balise ouverte, et l'exiger faisait perdre l'appel ENTIER — pas le dégrader, le perdre, en laissant
du XML brut dans la réponse affichée à l'utilisateur.
"""

from __future__ import annotations

from backend.inference.engines_adapters.adaptateur_llama_cpp import _appels_dans_le_texte


def _premier(texte: str) -> tuple[str, object]:
    appels = _appels_dans_le_texte(texte)
    assert len(appels) == 1, f"un appel attendu, {len(appels)} lus"
    fonction = appels[0]["function"]
    return fonction["name"], fonction["arguments"]


def test_dialecte_json_bien_forme() -> None:
    nom, arguments = _premier('<tool_call>{"name": "recherche_web", "arguments": {"requete": "orage"}}</tool_call>')
    assert nom == "recherche_web"
    assert arguments == {"requete": "orage"}


def test_dialecte_json_a_accolades_doublees() -> None:
    """Certains gabarits doublent les accolades en rendant l'exemple : le JSON reste lisible."""
    nom, arguments = _premier('<tool_call>{{"name": "recherche_web", "arguments": {{"requete": "orage"}}}}</tool_call>')
    assert nom == "recherche_web"
    assert arguments == {"requete": "orage"}


def test_dialecte_balise_bien_forme() -> None:
    texte = "<tool_call><function=executer_python><parameter=code>print(1)</parameter></function></tool_call>"
    nom, arguments = _premier(texte)
    assert nom == "executer_python"
    assert arguments == {"code": "print(1)"}


def test_dialecte_balise_hors_de_tool_call() -> None:
    """Certains gabarits émettent le balisage seul, sans enveloppe `<tool_call>`."""
    nom, arguments = _premier("<function=presenter_fichier><parameter=fichier_id>a.py</parameter></function>")
    assert nom == "presenter_fichier"
    assert arguments == {"fichier_id": "a.py"}


def test_fonction_non_fermee_reste_lue() -> None:
    """Génération arrêtée net : `</function>` manque, l'appel doit survivre."""
    nom, arguments = _premier("<function=executer_python><parameter=code>print(1)</parameter>")
    assert nom == "executer_python"
    assert arguments == {"code": "print(1)"}


def test_tool_call_non_ferme_reste_lu() -> None:
    nom, arguments = _premier('<tool_call>{"name": "recherche_web", "arguments": {"requete": "orage"}}')
    assert nom == "recherche_web"
    assert arguments == {"requete": "orage"}


def test_un_parametre_non_ferme_n_avale_pas_le_suivant() -> None:
    """Le cas dangereux : une valeur non bornée engloutirait les arguments suivants.

    Un `code` qui avale le reste de l'appel est pire qu'un argument manquant — il s'exécute.
    """
    texte = (
        "<function=recherche_web>"
        "<parameter=requete>orage"
        "<parameter=nombre_resultats>3</parameter>"
        "</function>"
    )
    nom, arguments = _premier(texte)
    assert nom == "recherche_web"
    assert arguments == {"requete": "orage", "nombre_resultats": "3"}


def test_appel_sans_argument_est_lu_tel_quel() -> None:
    """Observé le 2026-08-16 : le modèle émet la coquille vide. On la lit, l'outil la refusera.

    La lire plutôt que l'ignorer est délibéré : l'outil rend alors un échec explicite que le modèle
    peut corriger, là où un appel ignoré laissait son XML affiché sans que rien ne se passe.
    """
    nom, arguments = _premier("<function=executer_python></function>")
    assert nom == "executer_python"
    assert arguments == {}


def test_deux_appels_successifs() -> None:
    texte = (
        '<tool_call>{"name": "recherche_web", "arguments": {"requete": "a"}}</tool_call>'
        '<tool_call>{"name": "recherche_web", "arguments": {"requete": "b"}}</tool_call>'
    )
    appels = _appels_dans_le_texte(texte)
    assert [a["function"]["arguments"]["requete"] for a in appels] == ["a", "b"]


def test_texte_sans_appel_ne_produit_rien() -> None:
    assert _appels_dans_le_texte("Voici une réponse normale, qui parle de <tool_call> sans en ouvrir.") == []
