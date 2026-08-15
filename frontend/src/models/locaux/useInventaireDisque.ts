/*
 * Ce que le disque contient réellement, registre compris ou non.
 *
 * Séparé de `useModelesLocaux` à dessein : celui-ci liste ce qui est CHARGEABLE, celui-là ce qui
 * OCCUPE de la place. Les mélanger ferait apparaître comme modèle un dossier que le moteur ne peut
 * pas ouvrir — exactement la confusion que le registre existe pour éviter.
 */

import { useCallback, useEffect, useState } from 'react';

import { journal, messageErreur, obtenir, supprimer } from '../api/client';
import type { DossierDisque } from '../api/types';

export interface EtatInventaireDisque {
  readonly dossiers: readonly DossierDisque[];
  readonly erreur: string | null;
  readonly chargement: boolean;
  readonly rafraichir: () => void;
  readonly supprimerDossier: (dossier: string) => void;
}

export function useInventaireDisque(): EtatInventaireDisque {
  const [dossiers, setDossiers] = useState<readonly DossierDisque[]>([]);
  const [erreur, setErreur] = useState<string | null>(null);
  const [chargement, setChargement] = useState<boolean>(true);

  const rafraichir = useCallback((): void => {
    setChargement(true);
    obtenir<DossierDisque[]>('/models/disque')
      .then((recus) => {
        setDossiers(recus);
        setErreur(null);
      })
      .catch((cause: unknown) => {
        journal.erreur('inventaire du disque', cause);
        setErreur(messageErreur(cause));
      })
      .finally(() => setChargement(false));
  }, []);

  useEffect(() => rafraichir(), [rafraichir]);

  const supprimerDossier = useCallback(
    (dossier: string): void => {
      // Suppression irréversible : on relit le disque après coup plutôt que de retirer la ligne
      // localement. Ce qui s'affiche vient toujours d'une lecture, jamais d'une hypothèse.
      supprimer<{ octets_liberes: number }>(`/models/disque/${encodeURIComponent(dossier)}`)
        .catch((cause: unknown) => {
          journal.erreur(`suppression du dossier ${dossier}`, cause);
          setErreur(messageErreur(cause));
        })
        .finally(rafraichir);
    },
    [rafraichir],
  );

  return { dossiers, erreur, chargement, rafraichir, supprimerDossier };
}
