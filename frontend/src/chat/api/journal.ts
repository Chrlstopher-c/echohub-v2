/*
 * Puits de journalisation du domaine chat.
 * Le navigateur n'a pas pino : la console est le seul puits disponible. Le passer par un module
 * unique évite que le préfixe et le niveau soient réinventés à chaque appel réseau.
 */

const PREFIXE = '[chat]';

export interface Journal {
  info(message: string, details?: unknown): void;
  avertissement(message: string, details?: unknown): void;
  erreur(message: string, details?: unknown): void;
}

function ecrire(
  sortie: (message?: unknown, ...reste: unknown[]) => void,
  message: string,
  details: unknown,
): void {
  if (details === undefined) {
    sortie(`${PREFIXE} ${message}`);
    return;
  }
  sortie(`${PREFIXE} ${message}`, details);
}

export const journal: Journal = {
  info: (message, details) => ecrire(console.info, message, details),
  avertissement: (message, details) => ecrire(console.warn, message, details),
  erreur: (message, details) => ecrire(console.error, message, details),
};
