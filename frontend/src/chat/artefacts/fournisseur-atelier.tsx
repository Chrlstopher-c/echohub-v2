/*
 * Capacité d'ouvrir un artefact dans l'atelier, portée par contexte jusqu'aux cartes du fil.
 *
 * Par contexte et non par props, pour la même raison que `actions/fournisseur.tsx` : la carte vit
 * au fond de `FilMessages` → `Message` → `ReponseModele`, et faire descendre un rappel à travers
 * trois composants qui ne le regardent pas les couplerait tous à l'atelier.
 *
 * Hors fournisseur, la carte reste rendue mais inerte — un artefact affiché ailleurs que dans
 * l'écran de chat reste une information, pas un bouton mort qui lève.
 */

import { createContext, useContext } from 'react';
import type { ReactElement, ReactNode } from 'react';
import type { VersionArtefact } from './detection';

export interface CapacitesAtelier {
  /** Ouvre le panneau d'atelier sur cette version précise. */
  readonly ouvrirVersion: (version: VersionArtefact) => void;
  /** Artefact actuellement ouvert, pour marquer la carte active dans le fil ; `null` si aucun. */
  readonly artefactOuvert: string | null;
}

const Contexte = createContext<CapacitesAtelier | null>(null);

export interface FournisseurAtelierProps {
  readonly valeur: CapacitesAtelier;
  readonly children: ReactNode;
}

export function FournisseurAtelier({ valeur, children }: FournisseurAtelierProps): ReactElement {
  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

/** `null` hors fournisseur : la carte se rend alors sans action d'ouverture. */
export function useCapacitesAtelier(): CapacitesAtelier | null {
  return useContext(Contexte);
}
