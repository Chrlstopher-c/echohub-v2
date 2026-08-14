/*
 * Les variantes téléchargeables d'un dépôt, chacune avec sa faisabilité.
 *
 * Un dépôt GGUF héberge plusieurs quantifications du même modèle, et c'est à ce niveau que la
 * question « est-ce que ça tient ? » se pose vraiment : Q4_K_M tient, Q8_0 non. Un dépôt
 * safetensors n'a qu'une variante, le dossier entier.
 *
 * Fonctions pures : elles ne connaissent ni React ni le réseau.
 */

import type { ResultatRecherche } from '../api/types';
import { evaluer, type BudgetMemoire, type Faisabilite, type Verdict } from './evaluation';

export interface Variante {
  /** Fichier GGUF à télécharger, ou `null` quand l'unité est le dossier (safetensors). */
  fichier: string | null;
  /** Étiquette lue dans le nom de fichier — sert à distinguer, jamais à calculer. */
  etiquette: string | null;
  tailleOctets: number | null;
  faisabilite: Faisabilite;
}

export function variantes(resultat: ResultatRecherche, budget: BudgetMemoire): Variante[] {
  if (resultat.fichiers_gguf.length === 0) {
    return [
      {
        fichier: null,
        etiquette: resultat.formats[0] ?? null,
        tailleOctets: resultat.taille_totale_octets,
        faisabilite: evaluer(resultat.taille_totale_octets, budget),
      },
    ];
  }
  return resultat.fichiers_gguf.map((fichier) => ({
    fichier: fichier.nom,
    etiquette: fichier.etiquette,
    tailleOctets: fichier.taille_octets,
    faisabilite: evaluer(fichier.taille_octets, budget),
  }));
}

/* Ordre de préférence d'affichage — un classement, pas une mesure. */
const RANG: Record<Verdict, number> = { tient_vram: 3, deborde_ram: 2, ne_tient_pas: 1, indeterminee: 0 };

function taille(variante: Variante): number {
  return variante.tailleOctets ?? 0;
}

/**
 * Variante mise en avant sur la carte de résultat.
 *
 * Parmi celles qui tiennent en VRAM, la plus grosse : à quantification supérieure, qualité
 * supérieure, et l'utilisateur veut la meilleure qui rentre. Sinon la plus petite du meilleur rang,
 * c'est-à-dire celle qui s'approche le plus d'être chargeable.
 */
export function miseEnAvant(liste: readonly Variante[]): Variante | null {
  if (liste.length === 0) {
    return null;
  }
  const trie = [...liste].sort((a, b) => {
    const ecart = RANG[b.faisabilite.verdict] - RANG[a.faisabilite.verdict];
    if (ecart !== 0) {
      return ecart;
    }
    return b.faisabilite.verdict === 'tient_vram' ? taille(b) - taille(a) : taille(a) - taille(b);
  });
  return trie[0] ?? null;
}

export interface Repartition {
  tientVram: number;
  debordeRam: number;
  neTientPas: number;
}

/** Compte des variantes par verdict — la lecture d'un coup d'œil sur une carte de résultat. */
export function repartition(liste: readonly Variante[]): Repartition {
  return liste.reduce<Repartition>(
    (total, variante) => ({
      tientVram: total.tientVram + (variante.faisabilite.verdict === 'tient_vram' ? 1 : 0),
      debordeRam: total.debordeRam + (variante.faisabilite.verdict === 'deborde_ram' ? 1 : 0),
      neTientPas: total.neTientPas + (variante.faisabilite.verdict === 'ne_tient_pas' ? 1 : 0),
    }),
    { tientVram: 0, debordeRam: 0, neTientPas: 0 },
  );
}
