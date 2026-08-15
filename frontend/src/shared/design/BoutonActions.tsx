/*
 * Déclencheur visible du menu contextuel.
 *
 * Le clic droit n'existe pas au doigt et l'appui long entre en conflit avec la sélection de texte
 * et le menu natif du navigateur : sans ce bouton, toutes les actions d'une conversation ou d'un
 * message seraient inatteignables sur téléphone. Il est donc PERMANENT sous le seuil, jamais
 * conditionné à un survol.
 */

import type { ButtonHTMLAttributes, ReactElement } from 'react';
import { cn } from './cn';

export interface BoutonActionsProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Ce sur quoi portent les actions — « Actions sur la conversation », « Actions sur le message ». */
  readonly libelle: string;
}

export function BoutonActions({ libelle, className, ...reste }: BoutonActionsProps): ReactElement {
  return (
    <button
      type="button"
      aria-label={libelle}
      aria-haspopup="menu"
      title={libelle}
      className={cn(
        'inline-flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-sm',
        'lg:min-h-0 lg:min-w-0 lg:h-6 lg:w-6',
        'text-text-2 transition-colors duration-fast hover:bg-surface-2 hover:text-text',
        'focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--ring)]',
        className,
      )}
      {...reste}
    >
      <svg viewBox="0 0 16 16" className="h-4 w-4" fill="currentColor" aria-hidden="true">
        <circle cx="3.5" cy="8" r="1.35" />
        <circle cx="8" cy="8" r="1.35" />
        <circle cx="12.5" cy="8" r="1.35" />
      </svg>
    </button>
  );
}
