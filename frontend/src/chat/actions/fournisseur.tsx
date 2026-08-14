/*
 * Capacités d'action offertes sur chaque message du fil, portées par contexte.
 *
 * Par contexte et non par props : le fil rend une liste de `Message`, et faire descendre huit
 * rappels à travers `FilMessages` coupleraient le composant de liste à des actions qui ne le
 * regardent pas. Hors fournisseur, le contexte vaut `null` et un message reste un message —
 * l'enveloppe rend son contenu sans rien y ajouter, elle ne lève pas.
 *
 * Le fichier ne s'appelle pas `contexte` : dans ce projet, « contexte » désigne le contexte du
 * modèle (KV cache, voir `chat/contexte/`). Réutiliser le mot ici rendrait les deux illisibles.
 */

import { createContext, useContext } from 'react';
import type { ReactElement, ReactNode } from 'react';
import type { MessageChat } from '../api/contrats';

export interface ActionsMessages {
  /**
   * `variantes[id]` : frères du message, lui compris, dans l'ordre de création — tel que le serveur
   * les a établis. Clé absente ⇒ ce message n'a pas de variante ; ce n'est pas une donnée manquante.
   */
  variantes: Record<string, string[]>;
  /** Une génération occupe déjà le moteur : les actions restent VISIBLES mais refusées, et le disent. */
  occupe: boolean;
  /** Message actuellement ouvert en édition, `null` si aucun. */
  messageEnEdition: string | null;
  demarrerEdition: (message: MessageChat) => void;
  annulerEdition: () => void;
  confirmerEdition: (message: MessageChat, contenu: string) => void;
  rejouer: (message: MessageChat) => void;
  /** Bascule la vue sur la branche qui contient ce message — l'appel des flèches « ‹ 2 / 3 › ». */
  activerVariante: (messageId: string) => void;
}

const Contexte = createContext<ActionsMessages | null>(null);

export interface FournisseurActionsProps {
  valeur: ActionsMessages;
  children: ReactNode;
}

export function FournisseurActions({ valeur, children }: FournisseurActionsProps): ReactElement {
  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

/** `null` hors fournisseur : l'appelant doit alors rendre le message tel quel. */
export function useActionsMessages(): ActionsMessages | null {
  return useContext(Contexte);
}
