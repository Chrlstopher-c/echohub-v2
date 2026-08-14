/*
 * Installation d'une version vLLM, suivie sur son flux SSE.
 *
 * La progression affichée est celle que le backend annonce, et il ne l'annonce qu'après avoir
 * réellement franchi une étape. Rien n'avance tout seul pendant les vingt minutes du `pip install` :
 * l'étape en cours est nommée, et c'est plus honnête qu'une barre qui rampe.
 *
 * Fermer le flux annule l'installation côté backend. On appelle malgré tout la route d'annulation
 * explicite : elle est le seul chemin qui garantisse la suppression du venv partiel.
 *
 * Découpe : `useFlux` possède l'`EventSource`, `useSuivi` possède l'état affiché, et le hook public
 * ne fait que les relier. Aucun des trois ne dépasse la taille où l'on cesse de le relire en entier.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { journal, messageErreur, urlFlux } from '../api/client';
import { annulerInstallationVllm } from '../api/moteurs';
import { ROUTES } from '../api/routes';
import type { EvenementInstallation } from '../api/types';

/** Borne mémoire du journal affiché : un flux bavard ne doit pas faire enfler la page. */
const MAX_EVENEMENTS = 200;

export type PhaseInstallation = 'inactive' | 'en_cours' | 'terminee' | 'echouee';

export interface EtatInstallation {
  phase: PhaseInstallation;
  version: string | null;
  evenements: EvenementInstallation[];
  erreur: string | null;
  demarrer: (version: string, remplacer: boolean) => void;
  annuler: () => void;
}

interface Reactions {
  surEvenement: (evenement: EvenementInstallation) => void;
  surErreur: (message: string) => void;
}

function proprietes(valeur: unknown): Record<string, unknown> | null {
  // Cast justifié : la garde qui précède exclut `null` et tout ce qui n'est pas un objet.
  return valeur !== null && typeof valeur === 'object' ? (valeur as Record<string, unknown>) : null;
}

function estEvenement(valeur: unknown): valeur is EvenementInstallation {
  const objet = proprietes(valeur);
  // `etape` distingue un événement d'installation d'une erreur métier sérialisée dans le même
  // flux — le backend émet les deux formes sur le même canal.
  return objet !== null && typeof objet['etape'] === 'string' && typeof objet['message'] === 'string';
}

function messageDeCharge(valeur: unknown): string {
  const objet = proprietes(valeur);
  const message = objet === null ? undefined : objet['message'];
  if (typeof message === 'string') {
    return message;
  }
  return 'Le flux d’installation a renvoyé une charge inattendue.';
}

function traiter(donnees: string, reactions: Reactions): void {
  let charge: unknown;
  try {
    charge = JSON.parse(donnees);
  } catch (cause) {
    journal.erreur('événement SSE illisible', cause);
    reactions.surErreur('Événement illisible reçu sur le flux d’installation.');
    return;
  }
  if (estEvenement(charge)) {
    reactions.surEvenement(charge);
    return;
  }
  reactions.surErreur(messageDeCharge(charge));
}

interface Flux {
  ouvrir: (chemin: string, reactions: Reactions, surCoupure: () => void) => void;
  fermer: () => void;
  ouvert: () => boolean;
}

/** Possession de l'`EventSource` : une seule instance vivante, toujours fermée au démontage. */
function useFlux(): Flux {
  const source = useRef<EventSource | null>(null);

  const fermer = useCallback((): void => {
    source.current?.close();
    source.current = null;
  }, []);

  const ouvrir = useCallback(
    (chemin: string, reactions: Reactions, surCoupure: () => void): void => {
      fermer();
      const courant = new EventSource(urlFlux(chemin));
      source.current = courant;
      courant.onmessage = (message: MessageEvent<string>): void => traiter(message.data, reactions);
      courant.onerror = surCoupure;
    },
    [fermer],
  );

  useEffect(() => fermer, [fermer]);
  return useMemo(() => ({ ouvrir, fermer, ouvert: (): boolean => source.current !== null }), [ouvrir, fermer]);
}

interface Suivi {
  phase: PhaseInstallation;
  evenements: EvenementInstallation[];
  erreur: string | null;
  reactions: Reactions;
  reinitialiser: () => void;
  /** Retour à l'état neutre, sans verdict : c'est ce que produit une annulation demandée. */
  arreter: () => void;
  echouer: (message: string) => void;
}

interface EtatSuivi {
  phase: PhaseInstallation;
  evenements: EvenementInstallation[];
  erreur: string | null;
}

function construireReactions(
  ajouter: (evenement: EvenementInstallation) => void,
  conclure: (reussite: boolean) => void,
  echouer: (message: string) => void,
): Reactions {
  return {
    surEvenement: (evenement) => {
      ajouter(evenement);
      if (evenement.termine) {
        conclure(evenement.succes === true);
      }
    },
    surErreur: echouer,
  };
}

/** État affiché du suivi. `fermer` est injecté : le suivi conclut, il ne possède pas le flux. */
function useSuivi(fermer: () => void): Suivi {
  const [etat, setEtat] = useState<EtatSuivi>({ phase: 'inactive', evenements: [], erreur: null });

  const conclure = useCallback(
    (reussite: boolean): void => {
      fermer();
      setEtat((actuel) => ({ ...actuel, phase: reussite ? 'terminee' : 'echouee' }));
    },
    [fermer],
  );

  const echouer = useCallback(
    (message: string): void => {
      setEtat((actuel) => ({ ...actuel, erreur: message }));
      conclure(false);
    },
    [conclure],
  );

  const ajouter = useCallback((evenement: EvenementInstallation): void => {
    setEtat((actuel) => ({ ...actuel, evenements: [...actuel.evenements, evenement].slice(-MAX_EVENEMENTS) }));
  }, []);

  const reactions = useMemo(() => construireReactions(ajouter, conclure, echouer), [ajouter, conclure, echouer]);
  const reinitialiser = useCallback((): void => setEtat({ phase: 'en_cours', evenements: [], erreur: null }), []);
  const arreter = useCallback((): void => setEtat((actuel) => ({ ...actuel, phase: 'inactive' })), []);

  return { ...etat, reactions, reinitialiser, arreter, echouer };
}

export function useInstallationVllm(): EtatInstallation {
  const [version, setVersion] = useState<string | null>(null);
  const flux = useFlux();
  const suivi = useSuivi(flux.fermer);

  const demarrer = useCallback(
    (demandee: string, remplacer: boolean): void => {
      setVersion(demandee);
      suivi.reinitialiser();
      flux.ouvrir(ROUTES.installationVllm(demandee, remplacer), suivi.reactions, () => {
        // `EventSource` signale aussi une fermeture serveur normale : seul un flux encore
        // référencé correspond à une coupure subie.
        if (flux.ouvert()) {
          suivi.echouer('Flux d’installation interrompu.');
        }
      });
    },
    [flux, suivi],
  );

  const annuler = useCallback((): void => {
    flux.fermer();
    suivi.arreter();
    if (version === null) {
      return;
    }
    annulerInstallationVllm(version).catch((cause: unknown) => {
      journal.erreur(`annulation de l'installation ${version}`, cause);
      suivi.echouer(messageErreur(cause));
    });
  }, [flux, suivi, version]);

  return { phase: suivi.phase, version, evenements: suivi.evenements, erreur: suivi.erreur, demarrer, annuler };
}
