/*
 * Vocabulaire des capacités filtrables.
 *
 * Un seul appel au montage, annulé au démontage : la liste ne change pas sous les pieds de
 * l'utilisateur. Tant qu'elle n'est pas arrivée, l'interface ne propose aucun filtre — elle
 * n'affiche pas une liste de secours écrite ici, qui filtrerait sur un vocabulaire différent de
 * celui du backend.
 */

import { useEffect, useMemo, useState } from 'react';
import { messageErreur } from '../api/client';
import { listerCapacites } from '../api/recherche';
import type { DefinitionCapacite } from '../api/types';
import { indexerCapacites, type CarteCapacites } from './capacites';

export interface VocabulaireCapacites {
  /** Ordre d'affichage publié par le backend — jamais retrié ici. */
  definitions: readonly DefinitionCapacite[];
  carte: CarteCapacites;
  erreur: string | null;
}

export function useDefinitionsCapacites(): VocabulaireCapacites {
  const [definitions, setDefinitions] = useState<readonly DefinitionCapacite[]>([]);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    const controleur = new AbortController();
    listerCapacites(controleur.signal)
      .then((liste) => {
        setDefinitions(liste);
        setErreur(null);
      })
      .catch((cause: unknown) => {
        // Une annulation n'est pas un échec : le composant est démonté, il n'y a plus rien à dire.
        if (!controleur.signal.aborted) {
          setErreur(messageErreur(cause));
        }
      });
    return (): void => controleur.abort();
  }, []);

  const carte = useMemo<CarteCapacites>(() => indexerCapacites(definitions), [definitions]);

  return { definitions, carte, erreur };
}
