"""Preuve que le socle impose la langue de réponse (plan d'exécution, L10-c).

Constaté le 2026-08-15 : le socle de prompt système du projet est en français, mais les modèles
répondent souvent en anglais, y compris leur raisonnement — rien dans le texte ne le leur
interdisait. `construire()` doit désormais porter une consigne de langue explicite, dans les DEUX
formes du socle (avec et sans outil), puisque les deux sont concaténées telles quelles au prompt
de conversation (`composer`).
"""

from __future__ import annotations

from backend.outils.contrat import DescriptionOutil
from backend.outils.socle import construire

_OUTIL_FACTICE = (
    DescriptionOutil(nom="outil_factice", description="Outil de test.", parametres={"type": "object"}),
)


def test_le_socle_sans_outil_impose_le_francais() -> None:
    texte = construire(())
    assert "français" in texte
    assert texte.index("français") < texte.index("Tu tournes en local")


def test_le_socle_avec_outils_impose_aussi_le_francais() -> None:
    texte = construire(_OUTIL_FACTICE)
    assert "français" in texte
    assert texte.index("français") < texte.index("outil_factice")
