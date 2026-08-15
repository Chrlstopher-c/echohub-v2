/* Registre local — index de ce qui est réellement présent sur le disque. */

import { envoyer, obtenir, poster, supprimer } from './client';
import { ROUTES } from './routes';
import type { ModeleEnregistre, RapportCoherence, ResumeSynchronisation } from './types';

export function listerModelesLocaux(signal?: AbortSignal): Promise<ModeleEnregistre[]> {
  return obtenir<ModeleEnregistre[]>(ROUTES.registre, signal);
}

/** Réaligne le registre sur le disque : c'est le disque qui a raison, jamais l'index. */
/** Confronte ce que le modèle déclare à ce qu'il contient. Le rapport est rendu tel quel. */
export function verifierCoherence(identifiant: string): Promise<RapportCoherence> {
  return obtenir<RapportCoherence>(`${ROUTES.registre}/${encodeURIComponent(identifiant)}/coherence`);
}

/** Range ou retire un modèle des favoris. Rend l'entrée telle que la base la voit après coup. */
export function marquerFavori(identifiant: string, favori: boolean): Promise<ModeleEnregistre> {
  return envoyer<ModeleEnregistre>(`${ROUTES.registre}/${encodeURIComponent(identifiant)}/favori`, { favori });
}

export function synchroniserRegistre(): Promise<ResumeSynchronisation> {
  return poster<ResumeSynchronisation>(ROUTES.synchronisation);
}

/** Retire une entrée du registre sans toucher aux fichiers. */
export function oublierModele(identifiant: string): Promise<unknown> {
  return supprimer<unknown>(ROUTES.entreeRegistre(identifiant));
}
