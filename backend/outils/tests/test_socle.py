"""Preuve que le socle impose la langue de réponse, et qu'il est lui-même rédigé en anglais.

Constaté le 2026-08-15 : les modèles répondent souvent en anglais, y compris leur raisonnement —
rien dans le texte ne le leur interdisait. `construire()` porte donc une consigne de langue
explicite, dans les DEUX formes du socle (avec et sans outil), puisque les deux sont concaténées
telles quelles au prompt de conversation (`composer`).

Depuis le 2026-08-16, le socle est RÉDIGÉ EN ANGLAIS alors qu'il exige une sortie en français. Ce
n'est pas une contradiction : la langue du prompt et celle attendue en sortie sont deux choses
distinctes, et les dérivés Qwen3 chargés ici suivent mieux une instruction anglaise. Ces tests
vérifient donc les deux propriétés à la fois — la consigne existe, elle vient en premier, et le
corps du socle n'est plus en français.
"""

from __future__ import annotations

from backend.outils.contrat import DescriptionOutil
from backend.outils.socle import construire

_OUTIL_FACTICE = (
    DescriptionOutil(nom="outil_factice", description="Outil de test.", parametres={"type": "object"}),
)

# Mots français courants qui trahiraient un socle resté en français. Choisis pour ne pas exister en
# anglais : un faux positif rendrait ce test inutile.
_MOTS_FRANCAIS = ("Tu ", "aucun", "outils disponibles", "n'est", "peux")


def test_le_socle_sans_outil_impose_le_francais_en_premier() -> None:
    texte = construire(())
    assert "Write in French" in texte
    assert texte.index("Write in French") < texte.index("You run locally")


def test_le_socle_avec_outils_impose_le_francais_avant_de_les_lister() -> None:
    texte = construire(_OUTIL_FACTICE)
    assert "Write in French" in texte
    assert texte.index("Write in French") < texte.index("outil_factice")


def test_le_socle_est_redige_en_anglais() -> None:
    """La consigne de langue vise la SORTIE ; le socle, lui, parle au modèle dans sa langue forte."""
    for texte in (construire(()), construire(_OUTIL_FACTICE)):
        for mot in _MOTS_FRANCAIS:
            assert mot not in texte, f"le socle porte encore « {mot} » : corps resté en français"


def test_le_socle_exige_des_appels_complets() -> None:
    """Régression du 2026-08-16 : le modèle émettait des appels d'outil sans le moindre argument."""
    texte = construire(_OUTIL_FACTICE)
    assert "COMPLETE" in texte
    assert "empty call" in texte
