/* Lecture du profil matériel. Une seule route, mais elle mérite sa fonction typée. */

import { obtenir } from './client';
import { ROUTES } from './routes';
import type { ProfilMachine } from './types';

export function lireProfil(signal?: AbortSignal): Promise<ProfilMachine> {
  return obtenir<ProfilMachine>(ROUTES.profil, signal);
}
