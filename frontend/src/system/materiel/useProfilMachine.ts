/*
 * Profil matériel rafraîchi en continu.
 *
 * Interface publique du domaine `system` vers les autres domaines : le domaine `models` en dépend
 * pour situer une taille de modèle par rapport à la mémoire réellement libre. Personne ne lit
 * `api/profil` directement.
 */

import { useCallback } from 'react';
import { lireProfil } from '../api/profil';
import { useSondage, type EtatSondage } from '../api/sondage';
import type { ProfilMachine } from '../api/types';

/**
 * Deux secondes : assez pour voir la VRAM bouger pendant un chargement, assez lâche pour ne pas
 * lancer `nvidia-smi` en rafale — la mesure peut coûter plusieurs centaines de millisecondes.
 */
export const INTERVALLE_PROFIL_MS = 2000;

export type EtatProfil = EtatSondage<ProfilMachine>;

export function useProfilMachine(intervalleMs: number = INTERVALLE_PROFIL_MS): EtatProfil {
  const charger = useCallback((signal: AbortSignal): Promise<ProfilMachine> => lireProfil(signal), []);
  return useSondage<ProfilMachine>({ charger, intervalleMs });
}
