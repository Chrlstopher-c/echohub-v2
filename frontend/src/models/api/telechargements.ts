/* Téléchargements — démarrage, listage, annulation, reprise. */

import { obtenir, poster, supprimer } from './client';
import { ROUTES } from './routes';
import type { Telechargement } from './types';

export interface DemandeTelechargement {
  depot: string;
  /** Fichier GGUF précis. `null` pour un dépôt safetensors, où l'unité est le dossier entier. */
  fichier: string | null;
  revision?: string;
}

export function listerTelechargements(signal?: AbortSignal): Promise<Telechargement[]> {
  return obtenir<Telechargement[]>(ROUTES.telechargements, signal);
}

export function demarrerTelechargement(demande: DemandeTelechargement): Promise<Telechargement> {
  return poster<Telechargement>(ROUTES.telechargements, {
    depot: demande.depot,
    fichier: demande.fichier,
    revision: demande.revision ?? 'main',
  });
}

/**
 * Annule un transfert. Par défaut les octets déjà écrits sont CONSERVÉS : une reprise repart de là
 * et ne retélécharge rien. Supprimer est une décision distincte, jamais un effet de bord.
 */
export function annulerTelechargement(identifiant: string, supprimerFichiers = false): Promise<Telechargement> {
  return supprimer<Telechargement>(ROUTES.telechargement(identifiant, supprimerFichiers));
}

export function relancerTelechargement(identifiant: string): Promise<Telechargement> {
  return poster<Telechargement>(ROUTES.relance(identifiant));
}
