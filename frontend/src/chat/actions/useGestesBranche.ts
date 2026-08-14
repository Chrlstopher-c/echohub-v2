/*
 * Les trois gestes qui dérivent une conversation : rejouer, éditer, changer de variante.
 *
 * Aucun n'est destructeur — c'est le parti pris central de ce lot. Un rejeu ajoute une réponse
 * SŒUR sous le même parent, une édition ajoute un message sœur portant le nouveau texte, et la
 * bascule ne fait que déplacer le regard. Rien n'est réécrit, donc rien ne demande de confirmation :
 * une confirmation serait le symptôme d'une destruction qu'on aurait laissée possible.
 *
 * Chaque geste est refusé pendant qu'une génération occupe le moteur. Le backend le refuserait de
 * toute façon (`409 generation_deja_en_cours`) : l'écran le dit avant le clic plutôt qu'après.
 */

import { useCallback, useMemo, useState } from 'react';
import { messageErreur } from '../api/client';
import { activerBranche } from '../api/branches-api';
import type { EtatBranche, MessageChat } from '../api/contrats';
import { ouvrirFluxEdition, ouvrirFluxRejeu } from '../api/flux-generation';
import { journal } from '../api/journal';
import type { Bifurcation } from './apercu';
import type { Ouverture } from './useFluxBranche';

export interface ParametresGestes {
  conversationId: string | null;
  /** Une génération est déjà en cours : les gestes sont refusés. */
  occupe: boolean;
  poserBifurcation: (bifurcation: Bifurcation) => void;
  poserVue: (etat: EtatBranche) => void;
  lancer: (ouvrir: Ouverture) => Promise<void>;
}

export interface Gestes {
  messageEnEdition: string | null;
  erreur: string | null;
  demarrerEdition: (message: MessageChat) => void;
  annulerEdition: () => void;
  confirmerEdition: (message: MessageChat, contenu: string) => void;
  rejouer: (message: MessageChat) => void;
  activerVariante: (messageId: string) => void;
}

/** Contexte commun aux trois gestes : leurs entrées, plus les deux effets qu'ils partagent. */
interface Atelier extends ParametresGestes {
  /** Referme l'éditeur et efface l'échec affiché — tout geste repart d'un écran propre. */
  avantGeste: () => void;
  signaler: (erreur: string) => void;
}

/** Bascule de vue : la réponse du serveur EST la nouvelle vue, aucune relecture supplémentaire. */
async function basculer(
  conversationId: string,
  messageId: string,
  poserVue: (etat: EtatBranche) => void,
  signaler: (erreur: string) => void,
): Promise<void> {
  try {
    poserVue(await activerBranche(conversationId, messageId));
  } catch (cause) {
    journal.erreur('bascule de branche refusée', cause);
    signaler(messageErreur(cause));
  }
}

function useRejeu(atelier: Atelier): (message: MessageChat) => void {
  const { conversationId, occupe, poserBifurcation, lancer, avantGeste } = atelier;
  return useCallback(
    (message: MessageChat): void => {
      if (conversationId === null || occupe) {
        return;
      }
      avantGeste();
      // Un tour utilisateur est recopié en sœur puis regénéré : il RESTE sur le chemin. Une réponse
      // du modèle, elle, est remplacée par sa nouvelle sœur : elle en sort.
      poserBifurcation({ message_id: message.id, inclure: message.role === 'user', contenu: null });
      // `lancer` capture ses propres échecs et les expose par le flux : rien à propager ici.
      void lancer((rappels, signal) => ouvrirFluxRejeu(conversationId, message.id, {}, rappels, signal));
    },
    [conversationId, occupe, poserBifurcation, lancer, avantGeste],
  );
}

function useEnvoiEdition(atelier: Atelier): (message: MessageChat, contenu: string) => void {
  const { conversationId, occupe, poserBifurcation, lancer, avantGeste } = atelier;
  return useCallback(
    (message: MessageChat, contenu: string): void => {
      if (conversationId === null || occupe) {
        return;
      }
      avantGeste();
      poserBifurcation({ message_id: message.id, inclure: true, contenu });
      void lancer((rappels, signal) =>
        ouvrirFluxEdition(conversationId, message.id, { contenu }, rappels, signal),
      );
    },
    [conversationId, occupe, poserBifurcation, lancer, avantGeste],
  );
}

function useBascule(atelier: Atelier): (messageId: string) => void {
  const { conversationId, occupe, poserVue, avantGeste, signaler } = atelier;
  return useCallback(
    (messageId: string): void => {
      if (conversationId === null || occupe) {
        return;
      }
      avantGeste();
      // Échec capturé dans `basculer` puis exposé par `erreur`.
      void basculer(conversationId, messageId, poserVue, signaler);
    },
    [conversationId, occupe, poserVue, avantGeste, signaler],
  );
}

export function useGestesBranche(parametres: ParametresGestes): Gestes {
  const [messageEnEdition, setMessageEnEdition] = useState<string | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const avantGeste = useCallback((): void => {
    setMessageEnEdition(null);
    setErreur(null);
  }, []);
  const annulerEdition = useCallback((): void => setMessageEnEdition(null), []);
  const demarrerEdition = useCallback((message: MessageChat): void => {
    setErreur(null);
    setMessageEnEdition(message.id);
  }, []);

  const atelier: Atelier = { ...parametres, avantGeste, signaler: setErreur };
  const rejouer = useRejeu(atelier);
  const confirmerEdition = useEnvoiEdition(atelier);
  const activerVariante = useBascule(atelier);

  /*
   * Identité mémoïsée : cet objet part dans un contexte lu par chaque message du fil. Le recréer à
   * chaque rendu ferait re-rendre tout le fil à chaque token reçu — le défaut classique du contexte
   * en React, et exactement ce qu'un fil qui streame ne peut pas se permettre.
   */
  return useMemo(
    (): Gestes => ({
      messageEnEdition,
      erreur,
      demarrerEdition,
      annulerEdition,
      confirmerEdition,
      rejouer,
      activerVariante,
    }),
    [messageEnEdition, erreur, demarrerEdition, annulerEdition, confirmerEdition, rejouer, activerVariante],
  );
}
