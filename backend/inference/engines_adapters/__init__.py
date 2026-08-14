"""Adaptateurs de moteurs — interface publique du sous-module.

Ce que les autres modules ont le droit d'utiliser, et rien d'autre : le superviseur (qui garantit
l'exclusivité du GPU), le contrat de plan et d'options, le journal de chargement, la qualification
des échecs. Les adaptateurs concrets ne sont exposés que pour permettre des tests ciblés — le
chemin normal passe toujours par le superviseur, seul endroit qui applique l'exclusivité.

    from backend.inference.engines_adapters import PlanChargement, superviseur

    plan = PlanChargement.depuis_objet(plan_du_planificateur)
    await superviseur.demarrer_chargement(plan)
    statut = superviseur.statut()
"""

from backend.inference.engines_adapters.adaptateur_llama_cpp import AdaptateurLlamaCpp
from backend.inference.engines_adapters.adaptateur_vllm import AdaptateurVllm
from backend.inference.engines_adapters.base import AdaptateurMoteur
from backend.inference.engines_adapters.contrat import (
    CauseEchec,
    EtatChargement,
    EtatMoteur,
    MessageChat,
    MorceauGeneration,
    MoteurSupporte,
    OptionsGeneration,
    PlanChargement,
    Sante,
)
from backend.inference.engines_adapters.diagnostic import Diagnostic, EchecChargement, qualifier
from backend.inference.engines_adapters.journal import (
    EntreeJournal,
    SessionChargement,
    journal_chargement,
)
from backend.inference.engines_adapters.superviseur import (
    ChargementEnCours,
    StatutInference,
    SuperviseurInference,
    superviseur,
)
from backend.inference.engines_adapters.traduction_plan import vers_cause_planificateur, vers_plan_moteur
from backend.inference.engines_adapters.vram import MesureVram, lire_vram

__all__ = [
    # Pilotage
    "superviseur",
    "SuperviseurInference",
    "StatutInference",
    "ChargementEnCours",
    # Contrat
    "PlanChargement",
    "MoteurSupporte",
    "EtatChargement",
    "EtatMoteur",
    "MessageChat",
    "OptionsGeneration",
    "MorceauGeneration",
    "Sante",
    "CauseEchec",
    # Diagnostic et journal
    "Diagnostic",
    "EchecChargement",
    "qualifier",
    "EntreeJournal",
    "SessionChargement",
    "journal_chargement",
    # Frontière avec le planificateur
    "vers_plan_moteur",
    "vers_cause_planificateur",
    # Mesure
    "MesureVram",
    "lire_vram",
    # Adaptateurs concrets — usage réservé aux tests
    "AdaptateurMoteur",
    "AdaptateurLlamaCpp",
    "AdaptateurVllm",
]
