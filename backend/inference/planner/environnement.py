"""Variables d'environnement du processus de moteur, et celles qu'on refuse délibérément de poser.

Une variable **non posée** est une décision au même titre qu'une variable posée : elle apparaît donc
dans le plan, avec sa raison. C'est le seul moyen pour qu'un piège de plateforme reste visible au
lieu de se re-glisser dans le code six mois plus tard.

Piège de référence, mesuré le 2026-08-14 : sous WSL2, `GGML_CUDA_ENABLE_UNIFIED_MEMORY=1` fait
résider le modèle en RAM (20 Go occupés, VRAM figée à 2 Go, plusieurs minutes de chargement) parce
que WSL2 ne supporte pas la sur-souscription de mémoire managée. Après désactivation : 12 s de
chargement, 14,8 Go réellement en VRAM, 19,6 tok/s.
"""

from __future__ import annotations

from backend.inference.planner.entrees import Moteur, Plateforme, PreferencesUtilisateur, ProfilMachine
from backend.inference.planner.plan import VariableEnvironnement, VariableRefusee

NOM_MEMOIRE_UNIFIEE = "GGML_CUDA_ENABLE_UNIFIED_MEMORY"
NOM_GPU_VISIBLE = "CUDA_VISIBLE_DEVICES"

RAISON_WSL2 = (
    "WSL2 ne supporte pas la sur-souscription de mémoire managée : mesuré à 20 Go de RAM occupés "
    "et 2 Go de VRAM utilisée, modèle inexploitable. Le partage CPU/GPU passe par le placement "
    "décidé dans le plan — couches déléguées, ou tenseurs d'experts rappelés en mémoire hôte — "
    "jamais par la mémoire unifiée."
)


def construire_environnement(
    profil: ProfilMachine,
    preferences: PreferencesUtilisateur,
    moteur: Moteur,
    couches_cpu: int,
) -> tuple[tuple[VariableEnvironnement, ...], tuple[VariableRefusee, ...]]:
    """Environnement du moteur pour ce plan, et liste des variables écartées avec leur raison."""
    variables: list[VariableEnvironnement] = [
        VariableEnvironnement(
            nom=NOM_GPU_VISIBLE,
            valeur=str(profil.index_gpu),
            justification=f"Restreint le processus au GPU {profil.index_gpu} ({profil.nom_gpu or 'principal'}).",
        )
    ]
    refusees: list[VariableRefusee] = []
    _regler_memoire_unifiee(profil, preferences, moteur, couches_cpu, variables, refusees)
    return tuple(variables), tuple(refusees)


def _regler_memoire_unifiee(
    profil: ProfilMachine,
    preferences: PreferencesUtilisateur,
    moteur: Moteur,
    couches_cpu: int,
    variables: list[VariableEnvironnement],
    refusees: list[VariableRefusee],
) -> None:
    """Applique la règle de plateforme pour la mémoire unifiée CUDA. Sous WSL2, elle est interdite."""
    if moteur is not Moteur.LLAMA_CPP:
        return

    raison_refus = _raison_refus_memoire_unifiee(profil, preferences, couches_cpu)
    if raison_refus is not None:
        refusees.append(VariableRefusee(nom=NOM_MEMOIRE_UNIFIEE, raison=raison_refus))
        return

    variables.append(
        VariableEnvironnement(
            nom=NOM_MEMOIRE_UNIFIEE,
            valeur="1",
            justification=(
                f"Demandée, et {couches_cpu} couches restent côté CPU. Autorisée hors WSL2 uniquement : "
                "la sur-souscription de mémoire managée n'y fonctionne pas."
            ),
        )
    )


def _raison_refus_memoire_unifiee(
    profil: ProfilMachine,
    preferences: PreferencesUtilisateur,
    couches_cpu: int,
) -> str | None:
    """Raison de ne pas poser la variable, ou `None` si elle doit l'être."""
    if profil.plateforme is Plateforme.WSL2:
        # Refus inconditionnel, y compris quand l'utilisateur la demande : c'est un plafonnement de
        # préférence par une contrainte mesurée, pas un réglage discutable.
        return RAISON_WSL2
    if not preferences.autoriser_memoire_unifiee:
        return "Non demandée : le plan répartit déjà les couches explicitement entre GPU et CPU."
    if couches_cpu <= 0:
        return "Inutile : toutes les couches tiennent sur le GPU, rien n'a besoin de déborder."
    return None
