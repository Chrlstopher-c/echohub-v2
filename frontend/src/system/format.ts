/*
 * Mise en forme des mesures du domaine `system`.
 *
 * Toute valeur quantitative de l'interface passe par ici, en français et en base 1024 : un GPU
 * annonce ses 16 Go en gibioctets, les afficher en gigaoctets décimaux ferait apparaître 17,2 et
 * personne ne reconnaîtrait sa machine.
 */

const OCTETS_PAR_KO = 1024;
const UNITES = ['o', 'Ko', 'Mo', 'Go', 'To'] as const;

const UNE_DECIMALE = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const SANS_DECIMALE = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });

/** Valeur en gibioctets, une décimale, sans unité — pour composer « 8,2 / 14,7 Go ». */
export function enGo(octets: number): string {
  return UNE_DECIMALE.format(octets / OCTETS_PAR_KO ** 3);
}

/** Unité choisie selon la grandeur — pour des tailles hétérogènes (venvs, fichiers). */
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

/** Horodatage ISO du backend rendu en heure locale, à la seconde. */
export function heure(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
