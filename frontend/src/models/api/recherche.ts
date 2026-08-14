/* Recherche Hugging Face — appels typés, sans logique d'écran. */

import { obtenir } from './client';
import { ROUTES } from './routes';
import type { FormatRecherche, Ordre, PageRecherche, ResultatRecherche, TriRecherche } from './types';

export interface CritereRecherche {
  requete: string;
  formats: readonly FormatRecherche[];
  tri: TriRecherche;
  ordre: Ordre;
  page: number;
  taillePage: number;
}

export const CRITERE_INITIAL: CritereRecherche = {
  requete: '',
  formats: ['gguf'],
  tri: 'downloads',
  ordre: 'desc',
  page: 0,
  taillePage: 20,
};

export function rechercher(critere: CritereRecherche, signal?: AbortSignal): Promise<PageRecherche> {
  return obtenir<PageRecherche>(ROUTES.recherche(critere), signal);
}

/** Fiche d'un dépôt avec la taille annoncée de chaque fichier — base du choix de quantification. */
export function detailsDepot(depot: string, signal?: AbortSignal): Promise<ResultatRecherche> {
  return obtenir<ResultatRecherche>(ROUTES.depot(depot), signal);
}
