/*
 * État de santé des moteurs.
 *
 * Pas de sondage périodique ici, contrairement au profil matériel : vérifier un venv vLLM lance un
 * sous-processus Python et coûte plusieurs secondes. L'utilisateur déclenche la mesure, et il voit
 * l'horodatage de celle qu'il regarde.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { messageErreur } from '../api/client';
import { lireEtatMoteurs, type OptionsEtat } from '../api/moteurs';
import type { EtatMoteurs } from '../api/types';

export interface EtatMoteursHook {
  etat: EtatMoteurs | null;
  erreur: string | null;
  chargement: boolean;
  /** Relance la lecture ; `verifierVllm` sonde chaque venv et prend plusieurs secondes. */
  recharger: (options?: OptionsEtat) => void;
}

interface Mesure {
  etat: EtatMoteurs | null;
  erreur: string | null;
  chargement: boolean;
}

export function useMoteurs(): EtatMoteursHook {
  const [mesure, setMesure] = useState<Mesure>({ etat: null, erreur: null, chargement: true });
  const controleur = useRef<AbortController | null>(null);

  const recharger = useCallback((options: OptionsEtat = {}): void => {
    controleur.current?.abort();
    const courant = new AbortController();
    controleur.current = courant;
    setMesure((actuel) => ({ ...actuel, chargement: true }));
    lireEtatMoteurs(options, courant.signal)
      .then((resultat) => setMesure({ etat: resultat, erreur: null, chargement: false }))
      .catch((cause: unknown) => {
        if (!courant.signal.aborted) {
          setMesure((actuel) => ({ ...actuel, erreur: messageErreur(cause), chargement: false }));
        }
      });
  }, []);

  // Le contrôleur en cours est abandonné au démontage : aucune mise à jour d'état après coup.
  useEffect(() => {
    recharger();
    return (): void => controleur.current?.abort();
  }, [recharger]);

  return { ...mesure, recharger };
}
