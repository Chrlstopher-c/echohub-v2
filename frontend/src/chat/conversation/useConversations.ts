/*
 * Liste des conversations. Volontairement séparée du détail : ouvrir une conversation ne doit pas
 * recharger la liste, et créer une conversation ne doit pas recharger l'historique de la courante.
 */

import { useCallback, useEffect, useState } from 'react';
import { messageErreur } from '../api/client';
import type { ResumeConversation } from '../api/contrats';
import { creerConversation, listerConversations, supprimerConversation } from '../api/conversations-api';
import { journal } from '../api/journal';

const TITRE_PAR_DEFAUT = 'Nouvelle conversation';

export interface EtatConversations {
  conversations: ResumeConversation[];
  erreur: string | null;
  rafraichir: () => Promise<void>;
  creer: (modeleId: string | null) => Promise<ResumeConversation | null>;
  supprimer: (id: string) => Promise<void>;
}

export function useConversations(): EtatConversations {
  const [conversations, setConversations] = useState<ResumeConversation[]>([]);
  const [erreur, setErreur] = useState<string | null>(null);

  const rafraichir = useCallback(async (): Promise<void> => {
    try {
      setConversations(await listerConversations());
      setErreur(null);
    } catch (cause) {
      journal.erreur('liste des conversations indisponible', cause);
      setErreur(messageErreur(cause));
    }
  }, []);

  useEffect((): void => {
    void rafraichir();
  }, [rafraichir]);

  const creer = useCallback(
    async (modeleId: string | null): Promise<ResumeConversation | null> => {
      try {
        const creee = await creerConversation(TITRE_PAR_DEFAUT, modeleId);
        setConversations((actuelles) => [creee, ...actuelles]);
        return creee;
      } catch (cause) {
        journal.erreur('création de conversation refusée', cause);
        setErreur(messageErreur(cause));
        return null;
      }
    },
    [],
  );

  const supprimer = useCallback(async (id: string): Promise<void> => {
    try {
      await supprimerConversation(id);
      setConversations((actuelles) => actuelles.filter((conversation) => conversation.id !== id));
    } catch (cause) {
      journal.erreur('suppression de conversation refusée', cause);
      setErreur(messageErreur(cause));
    }
  }, []);

  return { conversations, erreur, rafraichir, creer, supprimer };
}
