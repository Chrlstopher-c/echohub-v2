/*
 * Assemblage de l'état de l'écran de chat : liste, conversation courante, plan et chargement.
 *
 * Réunir les quatre hooks ici garde le composant d'écran purement compositionnel, et surtout tient
 * en un seul endroit l'état `moteurPret` que l'écran affiche (badge, plan). Il ne conditionne PLUS
 * la saisie elle-même : le composeur reste actif sans modèle chargé, règle de l'opérateur
 * documentée dans `conversation/Composeur.tsx`.
 */

import { useCallback, useEffect, useState } from 'react';
import { useConversation, type EtatConversation } from './conversation/useConversation';
import { useConversations, type EtatConversations } from './conversation/useConversations';
import type { CibleChargement } from './plan/cible';
import { useChargement, type EtatChargementModele } from './plan/useChargement';
import { usePlan, type EtatPlan } from './plan/usePlan';

export interface EtatEcranChat {
  liste: EtatConversations;
  courante: EtatConversation;
  etatPlan: EtatPlan;
  chargement: EtatChargementModele;
  conversationActive: string | null;
  reglagesOuverts: boolean;
  moteurPret: boolean;
  choisirConversation: (id: string | null) => void;
  ouvrirReglages: (ouvert: boolean) => void;
  creerConversation: () => void;
  supprimerConversation: (id: string) => void;
  renommerConversation: (id: string, titre: string) => void;
}

export function useEcranChat(cible: CibleChargement | null): EtatEcranChat {
  const [conversationActive, setConversationActive] = useState<string | null>(null);
  const [reglagesOuverts, setReglagesOuverts] = useState<boolean>(false);
  const liste = useConversations();
  const courante = useConversation(conversationActive);
  const etatPlan = usePlan(cible?.demande ?? null);
  const chargement = useChargement();

  // Ouvrir la conversation la plus récente évite d'accueillir l'utilisateur sur un écran vide.
  useEffect((): void => {
    const recente = liste.conversations[0];
    if (conversationActive === null && recente !== undefined) {
      setConversationActive(recente.id);
    }
  }, [conversationActive, liste.conversations]);

  const modeleId = cible?.demande.metadonnees.identifiant ?? null;
  const creerConversation = useCallback((): void => {
    void liste.creer(modeleId).then((creee): void => {
      if (creee !== null) {
        setConversationActive(creee.id);
      }
    });
  }, [liste, modeleId]);

  const supprimerConversation = useCallback(
    (id: string): void => {
      void liste.supprimer(id);
      setConversationActive((actuelle) => (actuelle === id ? null : actuelle));
    },
    [liste],
  );

  return {
    liste,
    courante,
    etatPlan,
    chargement,
    conversationActive,
    reglagesOuverts,
    moteurPret: chargement.statut?.etat === 'pret',
    choisirConversation: setConversationActive,
    ouvrirReglages: setReglagesOuverts,
    creerConversation,
    supprimerConversation,
    renommerConversation: (id: string, titre: string): void => void liste.renommer(id, titre),
  };
}
