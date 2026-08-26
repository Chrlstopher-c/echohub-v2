/*
 * Ancienneté lisible d'une conversation — « 5 min », « 3 h », « hier », « 12 août ».
 *
 * L'échelle s'arrête au jour près : la liste sert à retrouver une conversation, pas à horodater
 * une mesure. Les minutes et heures suffisent tant que c'est récent ; au-delà, la date parle
 * mieux qu'un « il y a 26 jours » qu'il faudrait recalculer de tête.
 */

const MINUTE_MS = 60_000;
const HEURE_MS = 3_600_000;
const JOUR_MS = 86_400_000;

const FORMAT_JOUR = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' });
const FORMAT_ANNEE = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });

/** `maintenant` est injectable pour les tests ; l'horloge réelle partout ailleurs. */
export function anciennete(horodatage: string, maintenant: number = Date.now()): string {
  const date = new Date(horodatage);
  const ecart = maintenant - date.getTime();
  if (Number.isNaN(date.getTime())) {
    // Une date illisible ne doit ni lever ni afficher « NaN » : la ligne perd sa mesure, c'est tout.
    return '';
  }
  if (ecart < MINUTE_MS) {
    return 'à l’instant';
  }
  if (ecart < HEURE_MS) {
    return `${Math.floor(ecart / MINUTE_MS)} min`;
  }
  if (ecart < JOUR_MS) {
    return `${Math.floor(ecart / HEURE_MS)} h`;
  }
  if (ecart < 2 * JOUR_MS) {
    return 'hier';
  }
  const memeAnnee = new Date(maintenant).getFullYear() === date.getFullYear();
  return (memeAnnee ? FORMAT_JOUR : FORMAT_ANNEE).format(date);
}
