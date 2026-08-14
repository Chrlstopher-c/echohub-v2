/*
 * Navigation entre les variantes d'un même tour : « ‹ 2 / 3 › ».
 *
 * Visible en permanence, jamais au survol : ce n'est pas une action mais une INFORMATION — il
 * existe deux autres réponses à cet endroit. La cacher jusqu'au survol rendrait l'existence des
 * branches invisible, donc inutilisable.
 *
 * Position et total sont lus dans `variantes` tel que le serveur l'a servi. Aucun comptage local.
 */

import type { ReactElement } from 'react';
import { IconeChevronDroite, IconeChevronGauche } from './icones';

const CLASSE_FLECHE =
  'inline-flex h-4 w-4 items-center justify-center rounded-xs text-text-3 ' +
  'transition-colors duration-fast ease-out hover:text-text focus-visible:outline-none ' +
  'focus-visible:shadow-[0_0_0_2px_var(--ring)] disabled:opacity-35 disabled:hover:text-text-3';

export interface NavigationBranchesProps {
  /** Rang du message affiché parmi ses frères, à partir de 1. */
  position: number;
  total: number;
  /** Génération en cours : la bascule est refusée, mais les flèches restent lisibles. */
  occupe: boolean;
  onPrecedente: () => void;
  onSuivante: () => void;
}

export function NavigationBranches({
  position,
  total,
  occupe,
  onPrecedente,
  onSuivante,
}: NavigationBranchesProps): ReactElement {
  const titre = occupe ? 'Génération en cours' : undefined;
  return (
    <span className="inline-flex items-center gap-1 font-mono text-2xs tabular-nums text-text-3">
      <button
        type="button"
        className={CLASSE_FLECHE}
        onClick={onPrecedente}
        disabled={occupe || position <= 1}
        aria-label="Variante précédente de ce tour"
        title={titre}
      >
        <IconeChevronGauche />
      </button>
      <span aria-label={`Variante ${position} sur ${total}`}>
        {position} / {total}
      </span>
      <button
        type="button"
        className={CLASSE_FLECHE}
        onClick={onSuivante}
        disabled={occupe || position >= total}
        aria-label="Variante suivante de ce tour"
        title={titre}
      >
        <IconeChevronDroite />
      </button>
    </span>
  );
}
