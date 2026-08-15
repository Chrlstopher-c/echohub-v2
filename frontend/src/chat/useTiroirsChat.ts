/*
 * Quel tiroir du chat est ouvert sous le seuil de 1024 px.
 *
 * L'état vit dans l'écran, jamais dans les colonnes : `Feuille` les démonte au franchissement du
 * seuil, donc tout ce qu'elles porteraient de durable serait perdu au passage en paysage.
 *
 * Un seul tiroir ouvert à la fois — les deux panneaux couvrent le fil, en empiler deux ferait perdre
 * le repère de ce qu'on recouvre. Et le retour sur grand écran remet l'état à zéro : sinon un tiroir
 * ouvert avant la rotation rouvrirait tout seul au retour en portrait.
 */

import { useCallback, useEffect, useState } from 'react';
import { useEstGrandEcran } from '../shared/design';

export type TiroirChat = 'conversations' | 'plan' | null;

export interface EtatTiroirsChat {
  readonly tiroir: TiroirChat;
  readonly ouvrir: (cible: Exclude<TiroirChat, null>) => void;
  readonly fermer: () => void;
}

export function useTiroirsChat(): EtatTiroirsChat {
  const [tiroir, setTiroir] = useState<TiroirChat>(null);
  const estGrandEcran = useEstGrandEcran();

  useEffect((): void => {
    if (estGrandEcran) {
      setTiroir(null);
    }
  }, [estGrandEcran]);

  const ouvrir = useCallback((cible: Exclude<TiroirChat, null>): void => setTiroir(cible), []);
  const fermer = useCallback((): void => setTiroir(null), []);

  return { tiroir, ouvrir, fermer };
}
