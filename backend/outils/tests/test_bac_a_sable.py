"""Preuves du pont vers l'atelier (`bac_a_sable.py`).

Le confinement par `setuid`/`rlimits` a disparu : il vit désormais dans la frontière du conteneur
atelier, prouvée là-bas (image root+réseau, ressources bornées par Compose). Ce qui se prouve ICI,
sans conteneur ni base de données, c'est le CONTRAT du pont : il traduit un `racine_bac` de
conversation en dossier de l'atelier, il délègue, il rend le résultat, et il ne s'effondre jamais
quand l'atelier est absent.

L'exécution réelle passe par le stub local `atelier_local` (voir `conftest.py`), qui mocke à la
frontière du module `atelier` — l'intention des anciennes preuves (du vrai code exécuté) est
conservée, seul le conteneur distant est remplacé. Ces cas n'ont besoin ni de conversation ni de
magasin : ils fabriquent leur propre workspace, pour rester lisibles et indépendants du schéma.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.core.config import reset_settings_cache
from backend.outils import atelier, bac_a_sable


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Racine des espaces de travail, isolée par cas — comme `atelier_workspace` en production."""
    racine = tmp_path / "ateliers"
    monkeypatch.setenv("ATELIER_WORKSPACE", str(racine))
    reset_settings_cache()
    yield racine
    reset_settings_cache()


@pytest.fixture
def bac(workspace: Path) -> Path:
    """Dossier de travail d'une conversation fictive, sous le workspace."""
    return workspace / "conv-abc"


def test_preparer_bac_cree_le_dossier_sil_est_absent(bac: Path) -> None:
    assert not bac.exists()
    bac_a_sable.preparer_bac(bac)
    assert bac.is_dir()


def test_resoudre_refuse_un_chemin_absolu(bac: Path) -> None:
    with pytest.raises(bac_a_sable.CheminHorsBac):
        bac_a_sable.resoudre_dans_bac(bac, "/etc/passwd")


def test_resoudre_refuse_une_evasion_par_points(bac: Path) -> None:
    with pytest.raises(bac_a_sable.CheminHorsBac):
        bac_a_sable.resoudre_dans_bac(bac, "../../etc/passwd")


def test_sous_dossier_est_le_suffixe_relatif_au_workspace(bac: Path) -> None:
    """Seul le suffixe commun (`<conversation_id>`) voyage vers l'atelier, jamais un chemin absolu."""
    assert bac_a_sable._sous_dossier(bac) == "conv-abc"


def test_deux_conversations_ont_deux_sous_dossiers(workspace: Path) -> None:
    """(ex-preuve e) — deux bacs distincts se traduisent en deux dossiers d'atelier distincts."""
    assert bac_a_sable._sous_dossier(workspace / "conv-a") != bac_a_sable._sous_dossier(workspace / "conv-b")


def test_executer_commande_delegue_et_rend_la_sortie(bac: Path) -> None:
    """Délégation de bout en bout via le stub local : la commande tourne, la sortie revient mappée."""
    resultat = bac_a_sable.executer_commande_confinee("echo coucou-atelier", bac)
    assert resultat.code_retour == 0
    assert "coucou-atelier" in resultat.sortie
    assert resultat.tue_par_filet_securite is False


def test_executer_python_delegue_et_rend_la_sortie(bac: Path) -> None:
    resultat = bac_a_sable.executer_code_confine("print('depuis python')", bac)
    assert resultat.code_retour == 0
    assert "depuis python" in resultat.sortie


def test_atelier_injoignable_rend_un_message_actionnable(
    bac: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repli propre : atelier absent → résultat en échec au message actionnable, jamais un plantage."""
    def _injoignable(*_: object) -> atelier.ReponseAtelier:
        raise atelier.AtelierInjoignable(
            "L'atelier d'exécution n'est pas disponible (service non joignable). Démarrer l'atelier "
            "avec « docker compose up -d echohub-atelier »."
        )

    monkeypatch.setattr(bac_a_sable, "_executer_commande_atelier", _injoignable)

    resultat = bac_a_sable.executer_commande_confinee("echo jamais", bac)

    assert resultat.code_retour == -1
    assert resultat.tue_par_filet_securite is False
    assert "docker compose up -d echohub-atelier" in resultat.erreur


def test_limites_reelles_texte_dit_la_verite_de_l_atelier() -> None:
    """Le texte montré au modèle doit annoncer le vrai atelier : root, persistance, installation."""
    texte = bac_a_sable.LIMITES_REELLES_TEXTE
    assert "ATELIER" in texte
    assert "ROOT" in texte
    assert "PERSISTENT" in texte
    assert "isolé de la machine" in texte
