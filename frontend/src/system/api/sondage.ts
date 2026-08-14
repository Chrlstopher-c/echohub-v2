/*
 * Sondage périodique borné.
 *
 * La VRAM libre change en permanence : la seule façon honnête de l'afficher est de la redemander.
 * Deux garde-fous, tous deux volontaires :
 *
 * 1. l'attente est une chaîne de `setTimeout` relancée APRÈS la réponse, jamais un `setInterval` —
 *    un backend lent ne peut donc pas accumuler des requêtes qui se doublent ;
 * 2. la boucle se suspend après N échecs consécutifs. Un backend tombé ne doit pas produire une
 *    requête toutes les deux secondes jusqu'à la fin des temps ; l'utilisateur relance à la main.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { messageErreur } from './client';

export interface OptionsSondage<T> {
  charger: (signal: AbortSignal) => Promise<T>;
  intervalleMs: number;
  echecsMaxConsecutifs?: number;
}

export interface EtatSondage<T> {
  donnee: T | null;
  erreur: string | null;
  chargement: boolean;
  /** `true` quand la boucle s'est arrêtée sur sa borne d'échecs : plus rien n'est demandé. */
  suspendu: boolean;
  rafraichir: () => void;
}

const ECHECS_MAX_DEFAUT = 5;

type Issue<T> = { ok: true; donnee: T } | { ok: false; message: string };

interface Boucle<T> {
  charger: (signal: AbortSignal) => Promise<T>;
  intervalleMs: number;
  surDonnee: (donnee: T) => void;
  /** Retourne `true` pour programmer le tour suivant, `false` pour arrêter la boucle. */
  surEchec: (message: string) => boolean;
}

async function tenter<T>(charger: (signal: AbortSignal) => Promise<T>, signal: AbortSignal): Promise<Issue<T>> {
  try {
    return { ok: true, donnee: await charger(signal) };
  } catch (cause) {
    return { ok: false, message: messageErreur(cause) };
  }
}

/** Démarre la boucle et rend sa fonction d'arrêt — à brancher directement sur un `useEffect`. */
function lancerBoucle<T>(boucle: Boucle<T>): () => void {
  const controleur = new AbortController();
  let minuteur: number | undefined;
  let vivant = true;

  const executer = async (): Promise<void> => {
    const issue = await tenter(boucle.charger, controleur.signal);
    if (!vivant || controleur.signal.aborted) {
      return;
    }
    let continuer = true;
    if (issue.ok) {
      boucle.surDonnee(issue.donnee);
    } else {
      continuer = boucle.surEchec(issue.message);
    }
    if (continuer) {
      minuteur = window.setTimeout(() => void executer(), boucle.intervalleMs);
    }
  };

  void executer();
  return (): void => {
    vivant = false;
    controleur.abort();
    window.clearTimeout(minuteur);
  };
}

interface Interne<T> {
  donnee: T | null;
  erreur: string | null;
  chargement: boolean;
  suspendu: boolean;
}

export function useSondage<T>(options: OptionsSondage<T>): EtatSondage<T> {
  const { charger, intervalleMs, echecsMaxConsecutifs = ECHECS_MAX_DEFAUT } = options;
  const [etat, setEtat] = useState<Interne<T>>({ donnee: null, erreur: null, chargement: true, suspendu: false });
  const [reprise, setReprise] = useState<number>(0);
  const echecs = useRef<number>(0);

  const rafraichir = useCallback((): void => {
    echecs.current = 0;
    setEtat((actuel) => ({ ...actuel, chargement: true, suspendu: false }));
    setReprise((valeur) => valeur + 1);
  }, []);

  useEffect(() => {
    if (etat.suspendu) {
      return undefined;
    }
    return lancerBoucle<T>({
      charger,
      intervalleMs,
      surDonnee: (donnee) => {
        echecs.current = 0;
        setEtat({ donnee, erreur: null, chargement: false, suspendu: false });
      },
      surEchec: (message) => {
        echecs.current += 1;
        const suspendu = echecs.current >= echecsMaxConsecutifs;
        setEtat((actuel) => ({ ...actuel, erreur: message, chargement: false, suspendu }));
        return !suspendu;
      },
    });
  }, [charger, intervalleMs, echecsMaxConsecutifs, etat.suspendu, reprise]);

  return { ...etat, rafraichir };
}
