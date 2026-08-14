/*
 * Repères de débit MESURÉS, transcrits de COMPATIBILITE-GPU.md.
 *
 * Ce ne sont pas des prédictions et l'interface ne les interpole jamais : ce sont deux points
 * relevés sur une machine et un modèle précis. Ils sont affichés avec leur provenance, à côté du
 * réglage de contexte, parce qu'ils énoncent l'arbitrage central du produit — un contexte deux
 * fois plus grand a coûté la moitié du débit, sur le même GPU et le même modèle.
 *
 * Toute modification de ce fichier exige une nouvelle mesure, pas un raisonnement.
 */

export interface RepereDebit {
  contexte: number;
  tokensParSeconde: number;
}

/** Provenance exacte du relevé — affichée telle quelle, jamais résumée en « ~40 tok/s ». */
export const PROVENANCE_REPERES = 'RTX 5080 · Qwen3.6-35B-A3B IQ4_XS · 29/41 couches sur GPU';

// `as const` fige la liste en tuple : le premier repère existe alors pour le typage, ce qu'un
// `readonly RepereDebit[]` ne garantit pas. `satisfies` conserve la vérification de forme.
export const REPERES_DEBIT = [
  { contexte: 32_768, tokensParSeconde: 41.0 },
  { contexte: 57_344, tokensParSeconde: 19.6 },
] as const satisfies readonly RepereDebit[];

/*
 * Dernier contexte dont le débit mesuré est resté haut. Au-delà, la seule mesure disponible montre
 * une chute de 52 % : le rail du curseur passe en ambre à partir de là. Ce n'est pas un plafond —
 * le planificateur seul décide — c'est le signalement d'une zone où une mesure existe et prévient.
 */
export const CONTEXTE_DEBIT_MESURE_HAUT = REPERES_DEBIT[0].contexte;

/** Débit du repère le plus lent — sert d'échelle commune aux barres de comparaison. */
export const DEBIT_REPERE_MAX = Math.max(...REPERES_DEBIT.map((repere) => repere.tokensParSeconde));
