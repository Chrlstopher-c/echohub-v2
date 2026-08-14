"""Planificateur de chargement — cœur d'EchoHub v2 et seule source de vérité des paramètres.

Il répond à une question : *comment charger ce modèle sur cette machine, maintenant ?* Personne
d'autre ne décide d'un nombre de couches, d'un contexte ou d'une variable d'environnement — ni les
adaptateurs de moteur, ni l'API, ni le frontend, qui **affiche** le plan et ne le recalcule jamais.

Interface publique du sous-domaine :

    from backend.inference.planner import DemandeDeChargement, planifier, degrader

    plan = planifier(DemandeDeChargement(metadonnees=..., profil=..., preferences=...))
    # ... le moteur refuse le plan ...
    plan = degrader(demande, plan, CauseEchec.MEMOIRE_GPU_INSUFFISANTE)

Trois invariants, chacun né d'un défaut mesuré sur la v1 :

1. **Aucune constante magique** — le poids d'une couche vaut la taille réelle du fichier divisée
   par le nombre réel de couches lu dans l'en-tête, jamais une valeur supposée.
2. **Marge explicite** — cache KV, tampons de calcul et fragmentation sont provisionnés à partir du
   contexte et du batch demandés, chiffrés poste par poste dans `PlanDeChargement.budget`.
3. **Dégradation, jamais escalade** — après un échec, `degrader` ne rend qu'un plan strictement plus
   sobre, jusqu'à un mode minimal entièrement CPU.

Le module est pur : il ne lit ni le disque ni le GPU. Les mesures sont des **entrées**, produites
par les domaines `models` et `system`. C'est ce qui le rend testable sans matériel.
"""

from backend.inference.planner.budget import (
    BATCH_DEFAUT,
    CONTEXTE_PLANCHER,
    besoin_ram_octets,
    contexte_maximal,
    couches_attention,
    couches_gpu_maximales,
    largeur_activation_ffn,
    octets_kv_par_token_par_couche,
    poids_cumule_gpu_octets,
    poids_par_couche_octets,
)
from backend.inference.planner.entrees import (
    CauseEchec,
    DemandeDeChargement,
    FormatModele,
    MetadonneesModele,
    ModeleCharge,
    Moteur,
    Plateforme,
    PreferencesUtilisateur,
    ProfilMachine,
    TypeCacheKV,
)
from backend.inference.planner.environnement import NOM_GPU_VISIBLE, NOM_MEMOIRE_UNIFIEE
from backend.inference.planner.paliers import NIVEAU_MINIMAL, PALIERS
from backend.inference.planner.plan import (
    OCTETS_PAR_ELEMENT_KV,
    BudgetMemoire,
    EjectionRequise,
    PlanDeChargement,
    PosteMemoire,
    ValeurJustifiee,
    VariableEnvironnement,
    VariableRefusee,
)
from backend.inference.planner.planificateur import degrader, planifier

__all__ = [
    # Entrées
    "DemandeDeChargement",
    "MetadonneesModele",
    "ProfilMachine",
    "ModeleCharge",
    "PreferencesUtilisateur",
    "CauseEchec",
    "FormatModele",
    "Moteur",
    "Plateforme",
    "TypeCacheKV",
    # Sortie
    "PlanDeChargement",
    "BudgetMemoire",
    "PosteMemoire",
    "EjectionRequise",
    "ValeurJustifiee",
    "VariableEnvironnement",
    "VariableRefusee",
    # Planification
    "planifier",
    "degrader",
    "NIVEAU_MINIMAL",
    "PALIERS",
    # Arithmétique exposée pour l'affichage et les tests, jamais dupliquée ailleurs
    "poids_par_couche_octets",
    "poids_cumule_gpu_octets",
    "octets_kv_par_token_par_couche",
    "couches_attention",
    "largeur_activation_ffn",
    "couches_gpu_maximales",
    "contexte_maximal",
    "besoin_ram_octets",
    "OCTETS_PAR_ELEMENT_KV",
    "BATCH_DEFAUT",
    "CONTEXTE_PLANCHER",
    "NOM_GPU_VISIBLE",
    "NOM_MEMOIRE_UNIFIEE",
]
