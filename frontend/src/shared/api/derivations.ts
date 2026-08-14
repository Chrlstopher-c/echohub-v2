/*
 * Miroir des propriétés que le backend calcule mais NE SÉRIALISE PAS.
 *
 * `BudgetMemoire.vram_requise_octets`, `vram_restante_octets`, `PlanDeChargement.couches_cpu` et
 * `environnement` sont des `@property` Python, pas des `computed_field` : ils n'apparaissent donc
 * pas dans le JSON. Sans ce fichier, trois écrans réécriraient chacun la même somme.
 *
 * Frontière à ne pas franchir : ce sont des AGRÉGATS de valeurs déjà décidées — une addition, une
 * soustraction. Aucune fonction d'ici ne choisit un nombre de couches, un contexte ou un moteur.
 * Cette décision appartient au planificateur, et à lui seul.
 */

import type { BudgetMemoire, PlanDeChargement } from './types-plan';

/** Somme des postes du budget. Le backend en fait autant, à partir des mêmes postes. */
export function vramRequiseOctets(budget: BudgetMemoire): number {
  return budget.postes.reduce((total, poste) => total + poste.octets, 0);
}

/** Peut être négatif si le plan a été construit sur une mesure devenue caduque : le montrer. */
export function vramRestanteOctets(budget: BudgetMemoire): number {
  return budget.vram_disponible_octets - vramRequiseOctets(budget);
}

/** Couches restées côté CPU — les cellules en `--mem-ram` du langage visuel du plan. */
export function couchesCpu(plan: PlanDeChargement): number {
  return plan.couches_totales - plan.couches_gpu.valeur;
}

/** Environnement que le lanceur posera, mis à plat pour l'affichage. */
export function environnementDuPlan(plan: PlanDeChargement): Readonly<Record<string, string>> {
  return Object.fromEntries(plan.variables_environnement.map((variable) => [variable.nom, variable.valeur]));
}

/** Un plan replié : à présenter en `--caution`, avec sa raison, jamais comme un écran d'erreur. */
export function estPlanDegrade(plan: PlanDeChargement): boolean {
  return plan.niveau_degradation > 0;
}

/** Le plan exige de libérer le GPU avant de s'exécuter : le GPU est une ressource exclusive. */
export function exigeEjection(plan: PlanDeChargement): boolean {
  return plan.ejections_requises.length > 0;
}
