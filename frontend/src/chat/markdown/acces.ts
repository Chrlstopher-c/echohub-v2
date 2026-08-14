/*
 * Accès gardés et marqueur de syntaxe partagés par les lecteurs de blocs.
 *
 * `noUncheckedIndexedAccess` a raison de signaler les deux accès ci-dessous : une ligne au-delà du
 * tableau et un groupe de capture non apparié valent tous deux `undefined` au runtime. Plutôt que
 * de les taire par un cast, on les ramène à la chaîne vide — neutre pour toutes les opérations qui
 * suivent (`trim`, `startsWith`, `exec`), et jamais source d'un `undefined` propagé dans l'arbre.
 */

/* Défini ici, et pas dans chaque lecteur : `parseur.ts` ouvre les blocs de code, `liste.ts` doit
 * les reconnaître pour ne pas les avaler en texte. Deux copies de ce marqueur pourraient diverger. */
export const CLOTURE_CODE = '```';

export function ligneA(lignes: string[], index: number): string {
  return lignes[index] ?? '';
}

export function groupe(trouve: RegExpExecArray, rang: number): string {
  return trouve[rang] ?? '';
}
