/*
 * Client du domaine `system` — une seule route : le profil matériel mesuré à l'instant de l'appel.
 *
 * Aucune mise en cache ici, volontairement. Le profil est un instantané : la VRAM libre change
 * dès qu'un modèle est chargé, et un profil réutilisé produirait un plan calculé sur une machine
 * qui n'existe plus.
 */

import { requeteJson } from './transport';
import type { ProfilMachine } from './types-systeme';

/** La mesure lance `nvidia-smi` : quelques secondes sont normales, d'où un délai plus large. */
const DELAI_MESURE_MS = 45_000;

export function lireProfilMachine(signal?: AbortSignal): Promise<ProfilMachine> {
  return requeteJson<ProfilMachine>('/system/profil', { delaiMs: DELAI_MESURE_MS, signal });
}
