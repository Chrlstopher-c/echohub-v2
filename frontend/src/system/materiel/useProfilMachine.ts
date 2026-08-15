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
 * Douze secondes (L9) : chaque sondage rouvre une session NVML complète (`nvml.py`, `nvmlInit`/
 * `nvmlShutdown`), mesurée à 29 ms au premier appel puis 16 ms en natif — pas le sondage qui
 * coûtait cher, sa cadence à 2 s (30 cycles NVML/min/onglet). 12 s retenu après mesure HTTP réelle
 * (~40-50 ms/appel en natif, `curl` chronométré) : au milieu de la fourchette 10-15 s demandée,
 * avec marge si le conteneur GPU ajoute un coût que le natif ne peut pas révéler.
 */
export const INTERVALLE_PROFIL_MS = 12000;

export type EtatProfil = EtatSondage<ProfilMachine>;

export function useProfilMachine(intervalleMs: number = INTERVALLE_PROFIL_MS): EtatProfil {
  const charger = useCallback((signal: AbortSignal): Promise<ProfilMachine> => lireProfil(signal), []);
  return useSondage<ProfilMachine>({ charger, intervalleMs });
}
