/*
 * Suivi des téléchargements.
 *
 * Sondage de la liste entière plutôt qu'un flux par transfert : une seule requête par seconde
 * couvre tous les transferts, et la progression rendue est celle que le backend mesure sur le
 * disque, fragments compris. Rien n'est extrapolé entre deux relevés — une barre qui n'avance pas
 * signifie que rien n'a été écrit, et c'est une information.
 *
 * Le sondage s'arrête de lui-même dès qu'aucun transfert n'est actif, et après cinq échecs
 * consécutifs. Aucune boucle ne tourne sans raison ni sans borne.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { journal, messageErreur } from '../api/client';
import { annulerTelechargement, listerTelechargements, relancerTelechargement } from '../api/telechargements';
import type { Telechargement } from '../api/types';

const INTERVALLE_MS = 1000;
const ECHECS_MAX = 5;

const ETATS_ACTIFS: ReadonlySet<string> = new Set(['en_attente', 'en_cours']);

export function estActif(telechargement: Telechargement): boolean {
  return ETATS_ACTIFS.has(telechargement.etat);
}

export interface EtatTelechargements {
  liste: Telechargement[];
  erreur: string | null;
  chargement: boolean;
  actifs: number;
  rafraichir: () => void;
  annuler: (identifiant: string, supprimerFichiers: boolean) => void;
  relancer: (identifiant: string) => void;
}

interface Sondee {
  liste: Telechargement[];
  erreur: string | null;
  chargement: boolean;
}

interface ListeSondee extends Sondee {
  rafraichir: () => void;
}

type Poser = (transformer: (actuel: Sondee) => Sondee) => void;

/** Un tour de sondage. Retourne `true` s'il faut en programmer un autre. */
async function tour(controleur: AbortController, poser: Poser, echecs: { current: number }): Promise<boolean> {
  try {
    const resultat = await listerTelechargements(controleur.signal);
    echecs.current = 0;
    poser((actuel) => ({ ...actuel, liste: resultat, erreur: null }));
    return resultat.some(estActif);
  } catch (cause) {
    if (controleur.signal.aborted) {
      return false;
    }
    echecs.current += 1;
    poser((actuel) => ({ ...actuel, erreur: messageErreur(cause) }));
    return echecs.current < ECHECS_MAX;
  }
}

/** Sondage de la liste : relancé tant qu'un transfert est actif, arrêté sinon. */
function useListeSondee(): ListeSondee {
  const [etat, setEtat] = useState<Sondee>({ liste: [], erreur: null, chargement: true });
  const [reprise, setReprise] = useState<number>(0);
  const echecs = useRef<number>(0);

  const rafraichir = useCallback((): void => {
    echecs.current = 0;
    setReprise((valeur) => valeur + 1);
  }, []);

  useEffect(() => {
    const controleur = new AbortController();
    let minuteur: number | undefined;
    let vivant = true;
    const executer = async (): Promise<void> => {
      const suite = await tour(controleur, setEtat, echecs);
      if (!vivant) {
        return;
      }
      setEtat((actuel) => ({ ...actuel, chargement: false }));
      if (suite) {
        minuteur = window.setTimeout(() => void executer(), INTERVALLE_MS);
      }
    };
    void executer();
    return (): void => {
      vivant = false;
      controleur.abort();
      window.clearTimeout(minuteur);
    };
  }, [reprise]);

  return { ...etat, rafraichir };
}

export function useTelechargements(): EtatTelechargements {
  const sondee = useListeSondee();
  const { rafraichir } = sondee;

  const annuler = useCallback(
    (identifiant: string, supprimerFichiers: boolean): void => {
      annulerTelechargement(identifiant, supprimerFichiers)
        .catch((cause: unknown) => journal.erreur(`annulation du téléchargement ${identifiant}`, cause))
        .finally(rafraichir);
    },
    [rafraichir],
  );

  const relancer = useCallback(
    (identifiant: string): void => {
      relancerTelechargement(identifiant)
        .catch((cause: unknown) => journal.erreur(`relance du téléchargement ${identifiant}`, cause))
        .finally(rafraichir);
    },
    [rafraichir],
  );

  return { ...sondee, actifs: sondee.liste.filter(estActif).length, annuler, relancer };
}
