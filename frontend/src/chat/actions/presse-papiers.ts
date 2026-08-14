/*
 * Copie dans le presse-papiers — et surtout : ce qu'on fait quand le navigateur la refuse.
 *
 * EchoHub est servi en HTTP par nginx. `navigator.clipboard` n'existe QUE dans un contexte
 * sécurisé : sur `localhost` il est là, mais dès qu'on ouvre l'interface depuis une autre machine
 * du réseau (`http://192.168.x.x`) il disparaît. Une copie silencieusement perdue est pire que pas
 * de bouton du tout — l'utilisateur croit avoir le texte et colle autre chose. L'échec est donc une
 * VALEUR de retour, jamais une exception avalée.
 */

import { journal } from '../api/journal';

export type ResultatCopie = 'copiee' | 'refusee';

async function viaApiPressePapiers(texte: string): Promise<boolean> {
  // `isSecureContext` d'abord : hors contexte sécurisé, `navigator.clipboard` est simplement absent
  // dans Chrome et présent mais rejetant dans Firefox. Tester la capacité évite de dépendre du cas.
  if (!window.isSecureContext || typeof window.navigator.clipboard === 'undefined') {
    return false;
  }
  try {
    await window.navigator.clipboard.writeText(texte);
    return true;
  } catch (cause) {
    journal.avertissement('presse-papiers refusé par le navigateur', cause);
    return false;
  }
}

/*
 * Repli par sélection temporaire. `document.execCommand` est déprécié — c'est pourtant le SEUL
 * chemin disponible hors contexte sécurisé, et le refuser au nom de la dépréciation reviendrait à
 * retirer la fonction aux utilisateurs qui en ont le plus besoin.
 */
function viaSelectionTemporaire(texte: string): boolean {
  const zone = document.createElement('textarea');
  zone.value = texte;
  zone.setAttribute('readonly', '');
  // Hors flux et hors champ : la page ne doit ni sauter ni clignoter pendant la copie.
  zone.style.position = 'fixed';
  zone.style.top = '-1000px';
  zone.style.opacity = '0';
  document.body.appendChild(zone);
  try {
    zone.select();
    return document.execCommand('copy');
  } catch (cause) {
    journal.avertissement('copie par sélection temporaire refusée', cause);
    return false;
  } finally {
    zone.remove();
  }
}

/** Tente l'API moderne puis le repli. `refusee` signifie « rien n'a été copié », pas « peut-être ». */
export async function copierTexte(texte: string): Promise<ResultatCopie> {
  if (await viaApiPressePapiers(texte)) {
    return 'copiee';
  }
  return viaSelectionTemporaire(texte) ? 'copiee' : 'refusee';
}
