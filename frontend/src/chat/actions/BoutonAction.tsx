/*
 * Bouton d'une rangée d'actions. Carré de 20 px, icône seule, libellé porté par `aria-label`.
 *
 * `focus-visible` dessine l'anneau de focus : c'est ce qui rend la rangée utilisable au clavier une
 * fois qu'elle est révélée. Un bouton indisponible reste rendu et désactivé — jamais retiré.
 */

import type { ReactElement, ReactNode } from 'react';

const CLASSE =
  'inline-flex h-5 w-5 items-center justify-center rounded-xs text-text-2 ' +
  'transition-colors duration-fast ease-out hover:bg-surface-2 hover:text-text ' +
  'focus-visible:outline-none focus-visible:shadow-[0_0_0_2px_var(--ring)] ' +
  'disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-text-2';

export interface BoutonActionProps {
  /** Libellé lu par les technologies d'assistance ; l'icône seule n'énonce rien. */
  libelle: string;
  /** Infobulle native : dit ce que fait l'action, ou pourquoi elle est refusée. */
  titre: string;
  desactive: boolean;
  onClic: () => void;
  children: ReactNode;
}

export function BoutonAction({
  libelle,
  titre,
  desactive,
  onClic,
  children,
}: BoutonActionProps): ReactElement {
  return (
    <button
      type="button"
      className={CLASSE}
      onClick={onClic}
      disabled={desactive}
      aria-label={libelle}
      title={titre}
    >
      {children}
    </button>
  );
}
