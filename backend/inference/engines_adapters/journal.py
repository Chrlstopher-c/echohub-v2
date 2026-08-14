"""Journal de chargement : ce que le plan demandait, et ce qui s'est réellement passé.

Sans ce journal, un échec ne laisse qu'un message final ; on ignore quel plan a été appliqué, à
quelle étape le moteur a cédé, et combien de VRAM était libre à ce moment. La v1 obligeait à
relancer un chargement en regardant les logs défiler pour reconstituer cela.

Conservation volontairement bornée en mémoire : le journal sert au diagnostic de la session en
cours, pas à l'archivage. Les dix derniers chargements suffisent à comparer un échec à la réussite
qui l'a précédé.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any, Deque
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel, Field

from backend.core import maintenant
from backend.inference.engines_adapters.contrat import CauseEchec, EtatChargement, PlanChargement

SESSIONS_CONSERVEES = 10
ENTREES_PAR_SESSION_MAX = 200


class NiveauEntree(str, Enum):
    INFO = "info"
    AVERTISSEMENT = "avertissement"
    ERREUR = "erreur"


class EntreeJournal(BaseModel):
    """Un fait daté du chargement. `phase` situe l'étape, `details` porte les mesures."""

    horodatage: str = Field(default_factory=maintenant)
    phase: str
    niveau: NiveauEntree = NiveauEntree.INFO
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class SessionChargement(BaseModel):
    """Un chargement complet : son plan, son déroulé, son issue."""

    identifiant: str = Field(default_factory=lambda: uuid4().hex[:12])
    debut: str = Field(default_factory=maintenant)
    fin: str | None = None
    duree_s: float | None = None
    moteur: str
    modele: str
    plan: dict[str, Any]
    etat: EtatChargement = EtatChargement.EN_COURS
    cause: CauseEchec | None = None
    message: str = ""
    remediation: str = ""
    entrees: list[EntreeJournal] = Field(default_factory=list)


class JournalChargement:
    """Historique borné des chargements. Une seule instance partagée par le domaine inference."""

    def __init__(self, sessions_max: int = SESSIONS_CONSERVEES) -> None:
        self._sessions: Deque[SessionChargement] = deque(maxlen=sessions_max)

    def ouvrir(self, plan: PlanChargement) -> SessionChargement:
        """Démarre une session et fige le plan appliqué — le plan affiché est celui-là, pas un autre."""
        session = SessionChargement(
            moteur=plan.moteur.value,
            modele=plan.nom_affiche,
            plan=plan.model_dump(mode="json"),
        )
        self._sessions.append(session)
        return session

    def noter(
        self,
        session: SessionChargement | None,
        phase: str,
        message: str,
        *,
        niveau: NiveauEntree = NiveauEntree.INFO,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Ajoute un fait à la session et le reflète dans loguru — une seule écriture pour l'appelant."""
        journalise = {
            NiveauEntree.INFO: logger.info,
            NiveauEntree.AVERTISSEMENT: logger.warning,
            NiveauEntree.ERREUR: logger.error,
        }[niveau]
        journalise("[{}] {}", phase, message)

        if session is None:
            return
        if len(session.entrees) >= ENTREES_PAR_SESSION_MAX:
            session.entrees.pop(0)  # borne dure : un moteur bavard ne doit pas saturer la mémoire
        session.entrees.append(EntreeJournal(phase=phase, niveau=niveau, message=message, details=details or {}))

    def cloturer(
        self,
        session: SessionChargement | None,
        etat: EtatChargement,
        *,
        cause: CauseEchec | None = None,
        message: str = "",
        remediation: str = "",
        duree_s: float | None = None,
    ) -> None:
        """Fige l'issue d'une session. Toute session ouverte doit être close, y compris sur annulation."""
        if session is None:
            return
        session.etat = etat
        session.cause = cause
        session.message = message
        session.remediation = remediation
        session.fin = maintenant()
        session.duree_s = duree_s

    def sessions(self, limite: int = SESSIONS_CONSERVEES) -> list[SessionChargement]:
        """Sessions de la plus récente à la plus ancienne."""
        return list(reversed(list(self._sessions)))[: max(1, limite)]

    def derniere(self) -> SessionChargement | None:
        return self._sessions[-1] if self._sessions else None


# Instance partagée : le superviseur écrit, l'API lit. Aucun autre point d'écriture.
journal_chargement = JournalChargement()
