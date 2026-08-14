/* Registre local — index de ce qui est réellement présent sur le disque. */

import { obtenir, poster, supprimer } from './client';
import { ROUTES } from './routes';
import type { ModeleEnregistre, ResumeSynchronisation } from './types';

export function listerModelesLocaux(signal?: AbortSignal): Promise<ModeleEnregistre[]> {
  return obtenir<ModeleEnregistre[]>(ROUTES.registre, signal);
}

/** Réaligne le registre sur le disque : c'est le disque qui a raison, jamais l'index. */
export function synchroniserRegistre(): Promise<ResumeSynchronisation> {
  return poster<ResumeSynchronisation>(ROUTES.synchronisation);
}

/** Retire une entrée du registre sans toucher aux fichiers. */
export function oublierModele(identifiant: string): Promise<unknown> {
  return supprimer<unknown>(ROUTES.entreeRegistre(identifiant));
}
