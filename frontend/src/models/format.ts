/*
 * Mise en forme des mesures du domaine `models`.
 *
 * Base 1024, comme partout ailleurs dans le produit : une taille de modèle doit être comparable
 * d'un coup d'œil à une VRAM annoncée en gibioctets.
 */

const OCTETS_PAR_KO = 1024;
const UNITES = ['o', 'Ko', 'Mo', 'Go', 'To'] as const;

const UNE_DECIMALE = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const SANS_DECIMALE = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
const COMPACT = new Intl.NumberFormat('fr-FR', { notation: 'compact', maximumFractionDigits: 1 });

export function enGo(octets: number): string {
  return UNE_DECIMALE.format(octets / OCTETS_PAR_KO ** 3);
}

export function enGoUnite(octets: number): string {
  return `${enGo(octets)} Go`;
}

export function octetsLisibles(octets: number | null): string {
  if (octets === null) {
    return '—';
  }
  let valeur = Math.max(0, octets);
  let rang = 0;
  while (valeur >= OCTETS_PAR_KO && rang < UNITES.length - 1) {
    valeur /= OCTETS_PAR_KO;
    rang += 1;
  }
  const format = rang === 0 ? SANS_DECIMALE : UNE_DECIMALE;
  return `${format.format(valeur)} ${UNITES[rang]}`;
}

export function entier(valeur: number | null): string {
  return valeur === null ? '—' : SANS_DECIMALE.format(valeur);
}

/** Grands compteurs du Hub (téléchargements, mentions) — « 1,2 M » plutôt que sept chiffres. */
export function compact(valeur: number | null): string {
  return valeur === null ? '—' : COMPACT.format(valeur);
}

export function dateCourte(iso: string | null): string {
  if (iso === null) {
    return '—';
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('fr-FR');
}
