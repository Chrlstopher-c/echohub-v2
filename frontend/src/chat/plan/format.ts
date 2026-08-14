/*
 * Mise en forme des mesures. Un seul endroit décide comment un octet, un token ou un débit
 * s'écrivent — la cohérence des chiffres fait partie de la crédibilité de l'écran.
 *
 * Les tailles mémoire sont exprimées en unités binaires (1 Go = 1024³ octets) : c'est ce que
 * rapportent NVML et le fichier GGUF, et c'est la convention des mesures de COMPATIBILITE-GPU.md
 * (« 14,7 Go utilisables sur 16 »). Convertir en unités décimales ferait diverger l'affichage des
 * chiffres relevés sur la machine.
 */

const GIGA = 1024 ** 3;
const MEGA = 1024 ** 2;

const NOMBRE_1 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const NOMBRE_2 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ENTIER = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });

/** « 14,7 Go » au-dessus du gigaoctet, « 436 Mo » en dessous — jamais d'unité trompeuse. */
export function formaterOctets(octets: number): string {
  if (octets >= GIGA) {
    return `${NOMBRE_1.format(octets / GIGA)} Go`;
  }
  return `${ENTIER.format(Math.round(octets / MEGA))} Mo`;
}

export function formaterTokens(tokens: number): string {
  return ENTIER.format(tokens);
}

export function formaterDebit(tokensParSeconde: number): string {
  return `${NOMBRE_1.format(tokensParSeconde)} tok/s`;
}

export function formaterPourcentage(fraction: number): string {
  return `${NOMBRE_2.format(fraction * 100)} %`;
}

/** Durée écoulée d'un chargement : secondes tant que c'est lisible, minutes ensuite. */
export function formaterDuree(millisecondes: number): string {
  const secondes = millisecondes / 1000;
  if (secondes < 60) {
    return `${NOMBRE_1.format(secondes)} s`;
  }
  const minutes = Math.floor(secondes / 60);
  const reste = Math.floor(secondes % 60);
  return `${minutes} min ${String(reste).padStart(2, '0')} s`;
}

/** Heure seule d'un horodatage ISO — le journal de chargement tient dans une session. */
export function formaterHeure(horodatage: string): string {
  const date = new Date(horodatage);
  if (Number.isNaN(date.getTime())) {
    return '--:--:--';
  }
  return date.toLocaleTimeString('fr-FR', { hour12: false });
}
