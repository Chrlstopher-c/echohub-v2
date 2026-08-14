/*
 * Échelle commune aux jauges mémoire — fonctions pures, vérifiables sans DOM.
 *
 * Règle du design : une barre par ressource physique, à l'échelle RÉELLE. Si la VRAM totale vaut
 * 16 Go et la RAM 22 Go, la barre VRAM doit être visiblement plus courte. Normaliser les deux à
 * 100 % de leur largeur ferait croire à deux réservoirs de même taille — exactement le genre de
 * confort d'affichage qui masque la contrainte au lieu de la montrer.
 */

/** Ce qu'une barre a besoin de savoir pour se dessiner, tout étant déjà résolu en pourcentages. */
export interface JaugeMesuree {
  totalOctets: number;
  occupeOctets: number;
  libreOctets: number;
  /** Largeur de la barre entière, relative à la plus grande ressource affichée. */
  largeurPct: number;
  /** Part occupée à l'intérieur de la barre. */
  occupePct: number;
}

function borner(fraction: number): number {
  if (!Number.isFinite(fraction) || fraction <= 0) {
    return 0;
  }
  return Math.min(100, fraction * 100);
}

/**
 * Construit une jauge. `reference` est le total de la plus grande ressource affichée à l'écran :
 * c'est lui qui donne son sens à la comparaison entre deux barres.
 */
export function jauge(totalOctets: number, occupeOctets: number, reference: number): JaugeMesuree {
  const total = Math.max(0, totalOctets);
  const occupe = Math.min(Math.max(0, occupeOctets), total);
  return {
    totalOctets: total,
    occupeOctets: occupe,
    libreOctets: total - occupe,
    largeurPct: reference > 0 ? borner(total / reference) : 0,
    occupePct: total > 0 ? borner(occupe / total) : 0,
  };
}

/** Référence commune : le plus grand total parmi les ressources affichées ensemble. */
export function reference(...totaux: readonly number[]): number {
  return totaux.reduce((maximum, valeur) => (valeur > maximum ? valeur : maximum), 0);
}
