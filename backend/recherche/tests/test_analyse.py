"""Analyse de la charge JSON de SearXNG — le seul endroit où son schéma est interprété.

Les charges de test reproduisent les formes réellement rencontrées d'une version à l'autre :
`answers` en chaînes puis en objets, `unresponsive_engines` en couples puis en triplets,
`number_of_results` à zéro alors que des résultats existent. Ce sont ces divergences qui cassent
en silence — d'où des cas dédiés plutôt qu'une charge idéale.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from backend.recherche.analyse import analyser_page


def _charge(**surcharges: Any) -> dict[str, Any]:
    """Charge nominale à deux résultats, que chaque test dévie sur un seul point."""
    base: dict[str, Any] = {
        "query": "rtx 5080 vram",
        "number_of_results": 0,
        "results": [
            {
                "url": "https://example.org/a",
                "title": "  Premier résultat  ",
                "content": "Un extrait mesuré.",
                "engine": "duckduckgo",
                "engines": ["duckduckgo", "brave"],
                "score": 3.5,
                "publishedDate": "2026-03-04T10:15:00Z",
            },
            {
                "url": "https://example.org/b",
                "title": "Second résultat",
                "content": "   ",
                "engine": "wikipedia",
                "engines": [],
                "score": None,
            },
        ],
        "answers": [],
        "suggestions": ["rtx 5080 prix"],
        "unresponsive_engines": [],
    }
    base.update(surcharges)
    return base


def test_resultats_nominaux_lus_sans_perte() -> None:
    page = analyser_page(_charge())

    assert len(page.resultats) == 2
    premier = page.resultats[0]
    assert premier.titre == "Premier résultat"  # les espaces de bord sont retirés
    assert premier.url == "https://example.org/a"
    assert premier.extrait == "Un extrait mesuré."
    assert premier.moteur == "duckduckgo"
    assert premier.moteurs == ("duckduckgo", "brave")
    assert premier.score == 3.5
    assert page.suggestions == ("rtx 5080 prix",)


def test_champ_absent_ou_vide_vaut_none() -> None:
    """Un extrait fait d'espaces est une absence, pas une chaîne vide : le distinguer est le sujet."""
    page = analyser_page(_charge())
    second = page.resultats[1]

    assert second.extrait is None
    assert second.score is None
    assert second.publie_le is None
    assert second.moteurs == ()


def test_date_iso_avec_suffixe_z_est_lue_en_utc() -> None:
    """`fromisoformat` de Python 3.10 ne connaît pas le `Z` que les moteurs utilisent pourtant."""
    page = analyser_page(_charge())
    publie_le = page.resultats[0].publie_le

    assert publie_le is not None
    assert publie_le.utcoffset() == timedelta(0)
    assert publie_le.year == 2026 and publie_le.hour == 10


def test_date_illisible_est_ignoree_sans_casser_le_resultat() -> None:
    charge = _charge()
    charge["results"][0]["publishedDate"] = "hier matin"

    page = analyser_page(charge)

    assert len(page.resultats) == 2
    assert page.resultats[0].publie_le is None


def test_entree_sans_url_ni_titre_est_ecartee() -> None:
    """Une ligne non ouvrable n'est pas un résultat : la garder ferait passer un artefact pour une mesure."""
    charge = _charge()
    charge["results"].append({"title": "Sans URL", "content": "..."})
    charge["results"].append({"url": "https://example.org/c"})
    charge["results"].append("pas un objet")

    page = analyser_page(charge)

    assert len(page.resultats) == 2


def test_nombre_annonce_a_zero_devient_none() -> None:
    """SearXNG annonce très souvent 0 en rendant des résultats : ce 0 n'est pas une mesure."""
    assert analyser_page(_charge()).nombre_annonce is None
    assert analyser_page(_charge(number_of_results=1420)).nombre_annonce == 1420


def test_reponses_directes_dans_les_deux_formes() -> None:
    en_chaines = analyser_page(_charge(answers=["42", "  "]))
    en_objets = analyser_page(_charge(answers=[{"answer": "42", "url": "https://example.org"}]))

    assert en_chaines.reponses_directes == ("42",)
    assert en_objets.reponses_directes == ("42",)


def test_moteurs_muets_couples_triplets_et_chaines() -> None:
    charge = _charge(
        unresponsive_engines=[
            ["google", "timeout"],
            ["bing", "HTTP error", True],
            "startpage",
            [],
        ]
    )

    page = analyser_page(charge)

    assert [muet.moteur for muet in page.moteurs_muets] == ["google", "bing", "startpage"]
    assert page.moteurs_muets[0].raison == "timeout"
    assert page.moteurs_muets[2].raison is None


def test_charge_vide_ou_deformee_ne_leve_pas() -> None:
    """L'analyse écarte, elle ne lève pas : la décision d'échec appartient au service."""
    page = analyser_page({"results": "pas une liste", "suggestions": 12, "unresponsive_engines": None})

    assert page.resultats == ()
    assert page.suggestions == ()
    assert page.moteurs_muets == ()
    assert page.nombre_annonce is None
