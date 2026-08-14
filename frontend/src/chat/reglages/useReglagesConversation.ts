/*
 * Pilotage des réglages : ce qui est affiché, ce qui est enregistré, et l'écart entre les deux.
 *
 * Trois règles tiennent tout le fichier :
 *
 * 1. **L'enregistrement est différé, jamais bloquant.** Une frappe n'envoie rien ; le minuteur est
 *    relancé à chaque modification et la requête part quand la saisie se calme. Aucun bouton
 *    « Enregistrer » à ne pas oublier, aucun écran figé pendant l'aller-retour.
 * 2. **Le backend fait autorité sur ce qui est affiché.** La réponse du PATCH remplace le brouillon
 *    dès que l'utilisateur ne saisit plus rien — ce qu'il lit après un enregistrement est donc ce
 *    que le serveur a réellement retenu, pas ce que l'interface espérait lui avoir envoyé.
 * 3. **Un échec ne s'efface pas tout seul.** Il n'existe aucune reprise automatique : l'état porte
 *    la raison du refus jusqu'à ce que l'utilisateur réessaie ou modifie autre chose. Une boucle de
 *    retry silencieuse cacherait un refus permanent (valeur hors bornes) derrière du trafic.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import { messageErreur, patchJson } from '../api/client';
import { journal } from '../api/journal';
import type { CleReglage, MajParametres, MajReglages, Reglages } from './contrat';
import { construirePatch, reglagesModifies } from './patch';

/* Assez long pour absorber une frappe continue, assez court pour qu'un curseur relâché soit écrit. */
const DELAI_ENREGISTREMENT_MS = 600;

const CHEMIN_CONVERSATIONS = '/chat/conversations';

export type EtatEnregistrement =
  | { readonly type: 'a_jour' }
  | { readonly type: 'differe' }
  | { readonly type: 'en_cours' }
  | { readonly type: 'echoue'; readonly raison: string };

interface Ensemble {
  /** Dernière vérité connue du backend : réglages reçus à l'ouverture, puis réponses du PATCH. */
  readonly enregistre: Reglages;
  readonly brouillon: Reglages;
  readonly etat: EtatEnregistrement;
}

export interface PilotageReglages {
  /** Ce que le panneau affiche : le brouillon, seul état où une saisie en cours peut vivre. */
  readonly valeurs: Reglages;
  readonly enregistre: Reglages;
  /** Champs dont la valeur affichée n'a pas encore été confirmée par le backend. */
  readonly modifies: readonly CleReglage[];
  readonly etat: EtatEnregistrement;
  readonly modifierParametres: (patch: MajParametres) => void;
  readonly modifierPrompt: (promptSysteme: string) => void;
  readonly enregistrerMaintenant: () => void;
}

function depart(reglages: Reglages): Ensemble {
  return { enregistre: reglages, brouillon: reglages, etat: { type: 'a_jour' } };
}

/**
 * Repart de la vérité backend quand la conversation change. Le minuteur d'enregistrement posé au
 * même rendu est nettoyé au rendu suivant, bien avant son échéance : le brouillon de la
 * conversation précédente ne peut donc pas être écrit sur la nouvelle.
 */
function useRemiseAZero(conversationId: string, initiaux: Reglages, poser: (reglages: Reglages) => void): void {
  const derniers = useRef<Reglages>(initiaux);
  useEffect((): void => {
    derniers.current = initiaux;
  });
  useEffect((): void => {
    poser(derniers.current);
  }, [conversationId, poser]);
}

interface Differe {
  readonly ensemble: Ensemble;
  readonly marquerDiffere: () => void;
  readonly envoyer: (patch: MajReglages) => Promise<void>;
  /** Ce qui reste à écrire à l'instant t. Lu au démontage, jamais ailleurs. */
  readonly enAttente: MutableRefObject<MajReglages | null>;
}

/** Pose le minuteur, et le retire dès qu'une nouvelle modification arrive ou que l'écran part. */
function useEnregistrementDiffere({ ensemble, marquerDiffere, envoyer, enAttente }: Differe): void {
  const { enregistre, brouillon } = ensemble;
  useEffect((): (() => void) | undefined => {
    const patch = construirePatch(enregistre, brouillon);
    enAttente.current = patch;
    if (patch === null) {
      return undefined;
    }
    marquerDiffere();
    const minuteur = window.setTimeout((): void => {
      // Promesse volontairement non attendue : l'issue passe par l'état React, et le rejet est
      // traité dans `envoyer`. Il n'y a pas d'échec silencieux.
      void envoyer(patch);
    }, DELAI_ENREGISTREMENT_MS);
    return (): void => window.clearTimeout(minuteur);
  }, [enregistre, brouillon, marquerDiffere, envoyer, enAttente]);
}

/**
 * Fermer le panneau ne perd pas la dernière modification : le minuteur meurt avec le composant, la
 * requête part donc ici. Le patch n'est pas oublié quand une écriture est déjà en vol — le renvoyer
 * ne coûte qu'une requête, alors que l'oublier après un refus perdrait la saisie pour de bon.
 *
 * Limite assumée : plus personne n'est là pour afficher l'échec de cette dernière écriture, il ne
 * reste que la trace journalisée.
 */
function useEnvoiAuDemontage(
  enAttente: MutableRefObject<MajReglages | null>,
  envoyer: (patch: MajReglages) => Promise<void>,
): void {
  const dernierEnvoi = useRef(envoyer);
  useEffect((): void => {
    dernierEnvoi.current = envoyer;
  });
  useEffect((): (() => void) => {
    return (): void => {
      const patch = enAttente.current;
      if (patch !== null) {
        void dernierEnvoi.current(patch);
      }
    };
  }, [enAttente]);
}

/**
 * Références de suivi de l'écriture. Le rappel du parent en fait partie : gardé en référence, une
 * lambda recréée à chaque rendu du parent ne renouvelle plus `envoyer`, donc plus le minuteur —
 * sans quoi un écran qui se rafraîchit souvent (un flux en cours) repousserait l'enregistrement
 * indéfiniment.
 */
function useSuivi(onEnregistre?: (reglages: Reglages) => void): Suivi {
  const rappel = useRef<((reglages: Reglages) => void) | undefined>(onEnregistre);
  const numeroEcriture = useRef<number>(0);
  const revisionSaisie = useRef<number>(0);
  const enAttente = useRef<MajReglages | null>(null);
  useEffect((): void => {
    rappel.current = onEnregistre;
  });
  return { numeroEcriture, revisionSaisie, enAttente, rappel };
}

export function useReglagesConversation(
  conversationId: string,
  initiaux: Reglages,
  onEnregistre?: (reglages: Reglages) => void,
): PilotageReglages {
  const [ensemble, setEnsemble] = useState<Ensemble>(() => depart(initiaux));
  const suivi = useSuivi(onEnregistre);
  const poser = useCallback((reglages: Reglages): void => setEnsemble(depart(reglages)), []);
  useRemiseAZero(conversationId, initiaux, poser);

  const envoyer = useConfirmation(conversationId, setEnsemble, suivi);
  const marquerDiffere = useCallback((): void => {
    setEnsemble((precedent) =>
      precedent.etat.type === 'differe' ? precedent : { ...precedent, etat: { type: 'differe' } },
    );
  }, []);
  useEnregistrementDiffere({ ensemble, marquerDiffere, envoyer, enAttente: suivi.enAttente });
  useEnvoiAuDemontage(suivi.enAttente, envoyer);
  const modificateurs = useModificateurs(setEnsemble, suivi.revisionSaisie);
  const enregistrerMaintenant = useEnvoiImmediat(ensemble, envoyer);

  return {
    valeurs: ensemble.brouillon,
    enregistre: ensemble.enregistre,
    modifies: reglagesModifies(ensemble.enregistre, ensemble.brouillon),
    etat: ensemble.etat,
    modifierParametres: modificateurs.modifierParametres,
    modifierPrompt: modificateurs.modifierPrompt,
    enregistrerMaintenant,
  };
}

type PoseurEnsemble = (transformation: (precedent: Ensemble) => Ensemble) => void;

interface Suivi {
  readonly numeroEcriture: MutableRefObject<number>;
  readonly revisionSaisie: MutableRefObject<number>;
  readonly enAttente: MutableRefObject<MajReglages | null>;
  readonly rappel: MutableRefObject<((reglages: Reglages) => void) | undefined>;
}

/**
 * Écriture et adoption de la réponse. Deux compteurs, deux rôles distincts :
 * `numeroEcriture` ignore la réponse d'une requête qu'une plus récente a doublée ;
 * `revisionSaisie` dit si l'utilisateur a saisi quelque chose pendant l'aller-retour, auquel cas sa
 * frappe reste affichée et repartira au tour suivant.
 */
function useConfirmation(
  conversationId: string,
  setEnsemble: PoseurEnsemble,
  suivi: Suivi,
): (patch: MajReglages) => Promise<void> {
  const { numeroEcriture, revisionSaisie, rappel } = suivi;
  return useCallback(
    async (patch: MajReglages): Promise<void> => {
      numeroEcriture.current += 1;
      const jeton = numeroEcriture.current;
      const revision = revisionSaisie.current;
      setEnsemble((precedent) => ({ ...precedent, etat: { type: 'en_cours' } }));
      try {
        const recus = await patchJson<Reglages>(`${CHEMIN_CONVERSATIONS}/${conversationId}/reglages`, patch);
        if (jeton !== numeroEcriture.current) {
          return;
        }
        setEnsemble((precedent) => ({
          enregistre: recus,
          brouillon: revisionSaisie.current === revision ? recus : precedent.brouillon,
          etat: { type: 'a_jour' },
        }));
        rappel.current?.(recus);
      } catch (cause) {
        journal.erreur('réglages non enregistrés', cause);
        if (jeton !== numeroEcriture.current) {
          return;
        }
        setEnsemble((precedent) => ({ ...precedent, etat: { type: 'echoue', raison: messageErreur(cause) } }));
      }
    },
    [conversationId, setEnsemble, numeroEcriture, revisionSaisie, rappel],
  );
}

type Modificateurs = Pick<PilotageReglages, 'modifierParametres' | 'modifierPrompt'>;

function useModificateurs(setEnsemble: PoseurEnsemble, revisionSaisie: MutableRefObject<number>): Modificateurs {
  const modifierParametres = useCallback(
    (patch: MajParametres): void => {
      revisionSaisie.current += 1;
      setEnsemble((precedent) => ({
        ...precedent,
        brouillon: {
          ...precedent.brouillon,
          parametres: { ...precedent.brouillon.parametres, ...patch },
        },
      }));
    },
    [setEnsemble, revisionSaisie],
  );
  const modifierPrompt = useCallback(
    (promptSysteme: string): void => {
      revisionSaisie.current += 1;
      setEnsemble((precedent) => ({
        ...precedent,
        brouillon: { ...precedent.brouillon, prompt_systeme: promptSysteme },
      }));
    },
    [setEnsemble, revisionSaisie],
  );
  return { modifierParametres, modifierPrompt };
}

/** Réessai explicite après un refus : renvoie le même écart, sans attendre le minuteur. */
function useEnvoiImmediat(ensemble: Ensemble, envoyer: (patch: MajReglages) => Promise<void>): () => void {
  const { enregistre, brouillon } = ensemble;
  return useCallback((): void => {
    const patch = construirePatch(enregistre, brouillon);
    if (patch === null) {
      return;
    }
    void envoyer(patch);
  }, [enregistre, brouillon, envoyer]);
}
