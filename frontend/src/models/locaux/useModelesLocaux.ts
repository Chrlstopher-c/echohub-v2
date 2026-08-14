/*
 * Registre local.
 *
 * Pas de sondage : le contenu du disque ne change que sur action de l'utilisateur ou fin de
 * transfert, et l'écran déclenche alors une relecture. Sonder en continu ferait parcourir le
 * disque pour rien.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { journal, messageErreur } from '../api/client';
import { listerModelesLocaux, oublierModele, synchroniserRegistre } from '../api/registre';
import type { ModeleEnregistre } from '../api/types';

export interface EtatModelesLocaux {
  liste: ModeleEnregistre[];
  erreur: string | null;
  chargement: boolean;
  synchronisation: boolean;
  rafraichir: () => void;
  /** Réaligne le registre sur le disque — c'est le disque qui a raison, jamais l'index. */
  synchroniser: () => void;
  oublier: (identifiant: string) => void;
}

interface Registre {
  liste: ModeleEnregistre[];
  erreur: string | null;
  chargement: boolean;
}

interface Liste extends Registre {
  rafraichir: () => void;
}

function useListeRegistre(): Liste {
  const [etat, setEtat] = useState<Registre>({ liste: [], erreur: null, chargement: true });
  const controleur = useRef<AbortController | null>(null);

  const rafraichir = useCallback((): void => {
    controleur.current?.abort();
    const courant = new AbortController();
    controleur.current = courant;
    setEtat((actuel) => ({ ...actuel, chargement: true }));
    listerModelesLocaux(courant.signal)
      .then((resultat) => setEtat({ liste: resultat, erreur: null, chargement: false }))
      .catch((cause: unknown) => {
        if (!courant.signal.aborted) {
          setEtat((actuel) => ({ ...actuel, erreur: messageErreur(cause), chargement: false }));
        }
      });
  }, []);

  // Le contrôleur en cours est abandonné au démontage : aucune mise à jour d'état après coup.
  useEffect(() => {
    rafraichir();
    return (): void => controleur.current?.abort();
  }, [rafraichir]);

  return { ...etat, rafraichir };
}

export function useModelesLocaux(): EtatModelesLocaux {
  const registre = useListeRegistre();
  const { rafraichir } = registre;
  const [synchronisation, setSynchronisation] = useState<boolean>(false);

  const synchroniser = useCallback((): void => {
    setSynchronisation(true);
    synchroniserRegistre()
      .catch((cause: unknown) => journal.erreur('synchronisation du registre', cause))
      .finally(() => {
        setSynchronisation(false);
        rafraichir();
      });
  }, [rafraichir]);

  const oublier = useCallback(
    (identifiant: string): void => {
      oublierModele(identifiant)
        .catch((cause: unknown) => journal.erreur(`oubli du modèle ${identifiant}`, cause))
        .finally(rafraichir);
    },
    [rafraichir],
  );

  return { ...registre, synchronisation, synchroniser, oublier };
}
