/*
 * Texte des limites réelles du bac à sable (`backend/outils/api.py`), affiché tel quel à
 * l'utilisateur (plan d'exécution, section 2.6) — cet écran ne le réécrit ni ne l'embellit.
 */

import { getJson } from './client';

interface ReponseLimites {
  texte: string;
}

export function chargerLimitesBac(signal?: AbortSignal): Promise<string> {
  return getJson<ReponseLimites>('/outils/limites-bac', signal).then((reponse) => reponse.texte);
}
