/* Recherche Hugging Face — appels typés, sans logique d'écran. */

import { obtenir } from './client';
import { ROUTES } from './routes';
import type {
  Capacite,
  DefinitionCapacite,
  FormatRecherche,
  Ordre,
  PageRecherche,
  ResultatRecherche,
  TriRecherche,
} from './types';

export interface CritereRecherche {
  requete: string;
  formats: readonly FormatRecherche[];
  /** Capacités exigées, combinées en ET côté backend. Vide = aucun filtre de capacité. */
  capacites: readonly Capacite[];
  tri: TriRecherche;
  ordre: Ordre;
  page: number;
  taillePage: number;
}

export const CRITERE_INITIAL: CritereRecherche = {
  requete: '',
  formats: ['gguf'],
  capacites: [],
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

/**
 * Vocabulaire des capacités filtrables, tel que le backend le publie.
 *
 * Les filtres se composent à partir de cette liste et d'aucune autre : c'est elle qui filtre
 * réellement, et une copie locale des libellés divergerait au premier ajout de capacité.
 */
export function listerCapacites(signal?: AbortSignal): Promise<DefinitionCapacite[]> {
  return obtenir<DefinitionCapacite[]>(ROUTES.capacites, signal);
}
