/*
 * Faisabilité annoncée — le seul jugement porté AVANT téléchargement.
 *
 * Ce module ne planifie rien et ne prétend pas le faire. Le plan de chargement est calculé par le
 * backend à partir de l'en-tête GGUF réellement lu ; il n'existe qu'une fois le fichier présent.
 * Ici on ne dispose que de deux nombres : la taille que le Hub annonce pour un fichier, et la
 * mémoire mesurée à l'instant. On les compare, et on affiche les deux opérandes à côté du verdict —
 * pour qu'aucun chiffre ne semble sortir d'un modèle caché.
 *
 * Ce qui est délibérément absent : marge de sécurité, coût du cache KV, poids par couche, palier de
 * paramètres, facteur de quantification. Toute constante de ce genre serait exactement la faute que
 * la v2 corrige — la v1 annonçait 80 couches pour 41 réelles et 150 Mo par couche pour 436 mesurés.
 *
 * Fonctions pures, sans React ni réseau : le verdict se vérifie en injectant deux nombres.
 */

import type { ProfilMachine } from '../../system';
import { enGoUnite } from '../format';

export type Verdict = 'tient_vram' | 'deborde_ram' | 'ne_tient_pas' | 'indeterminee';

/** Mémoire libre mesurée à l'instant. `mesure` à `false` = aucun verdict défendable. */
export interface BudgetMemoire {
  readonly vramLibreOctets: number;
  readonly ramDisponibleOctets: number;
  readonly mesure: boolean;
}

export interface Faisabilite {
  readonly verdict: Verdict;
  /** Poids annoncés par le Hub. `null` quand le Hub ne les publie pas. */
  readonly poidsOctets: number | null;
  readonly budget: BudgetMemoire;
  /** Formule courte, affichée telle quelle : les opérandes réels de la comparaison. */
  readonly comparaison: string;
}

export const LIBELLE_VERDICT: Record<Verdict, string> = {
  tient_vram: 'tient en VRAM',
  deborde_ram: 'tient, couches en RAM',
  ne_tient_pas: 'ne tient pas',
  indeterminee: 'indéterminable',
};

/**
 * Ce que la comparaison ne couvre pas. Affiché une fois par écran, jamais escamoté : promettre un
 * verdict plus précis que ses entrées serait reproduire la v1 sous une autre forme.
 */
export const RESERVE =
  'Comparaison des poids annoncés par le Hub à la mémoire libre mesurée à l’instant. Le cache KV, ' +
  'les tampons d’exécution et le contexte choisi ne sont pas comptés : le plan réel est calculé ' +
  'après téléchargement, à partir de l’en-tête du fichier.';

const BUDGET_INCONNU: BudgetMemoire = { vramLibreOctets: 0, ramDisponibleOctets: 0, mesure: false };

/** Traduit un profil machine en budget. Le profil expose déjà ces deux valeurs calculées. */
export function budgetDepuis(profil: ProfilMachine | null): BudgetMemoire {
  if (profil === null || !profil.a_gpu) {
    return BUDGET_INCONNU;
  }
  return {
    vramLibreOctets: profil.vram_libre_octets,
    ramDisponibleOctets: profil.ram_disponible_octets,
    // La RAM peut être non mesurable ; la VRAM, elle, l'est dès qu'un GPU répond.
    mesure: true,
  };
}

function comparer(poidsOctets: number, budget: BudgetMemoire): Verdict {
  if (poidsOctets <= budget.vramLibreOctets) {
    return 'tient_vram';
  }
  if (poidsOctets <= budget.vramLibreOctets + budget.ramDisponibleOctets) {
    return 'deborde_ram';
  }
  return 'ne_tient_pas';
}

function formuler(poidsOctets: number, budget: BudgetMemoire): string {
  return (
    `${enGoUnite(poidsOctets)} annoncés · ${enGoUnite(budget.vramLibreOctets)} de VRAM libre · ` +
    `${enGoUnite(budget.ramDisponibleOctets)} de RAM disponible`
  );
}

export function evaluer(poidsOctets: number | null, budget: BudgetMemoire): Faisabilite {
  if (!budget.mesure) {
    return { verdict: 'indeterminee', poidsOctets, budget, comparaison: 'Mémoire de la machine non mesurée.' };
  }
  if (poidsOctets === null || poidsOctets <= 0) {
    return { verdict: 'indeterminee', poidsOctets, budget, comparaison: 'Le Hub n’annonce pas la taille.' };
  }
  return {
    verdict: comparer(poidsOctets, budget),
    poidsOctets,
    budget,
    comparaison: formuler(poidsOctets, budget),
  };
}
