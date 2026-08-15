/*
 * Barre segmentée + légende chiffrée de la fenêtre de contexte.
 *
 * Deux partis pris qui décident du reste :
 *
 * 1. **Aucune largeur minimale de segment.** Un plancher de quelques pixels ferait paraître un
 *    poste à 0,2 % aussi gros qu'un poste à 1 % : la barre mentirait précisément là où elle est
 *    censée arbitrer. Un poste minuscule devient invisible dans la barre — et reste entièrement
 *    lisible dans la légende, qui porte son nom, ses tokens et son pourcentage exacts.
 * 2. **Rien n'est recalculé ici.** Les parts arrivent mesurées et rapportées au contexte servi ;
 *    ce composant les met en forme, il n'en dérive aucune.
 */

import { motion } from 'framer-motion';
import type { ReactElement } from 'react';
import type { PartContexte } from '../../shared/api';
import { TONE_VAR, Tooltip, transitionLayout } from '../../shared/design';
import { DESCRIPTION_POSTE, LIBELLE_POSTE, TONE_POSTE, formaterPart, formaterTokens } from './postes';

/** Trait rouge à l'intérieur du cadre quand la conversation excède la fenêtre servie. */
const CADRE_DEPASSEMENT = 'inset 0 0 0 1px var(--critical)';

function Segment({ part }: { part: PartContexte }): ReactElement {
  return (
    <motion.span
      className="block h-full"
      initial={false}
      animate={{ width: `${(part.part * 100).toFixed(4)}%` }}
      transition={transitionLayout}
      style={{ backgroundColor: TONE_VAR[TONE_POSTE[part.poste]] }}
    />
  );
}

function Ligne({ part }: { part: PartContexte }): ReactElement {
  const libelle = LIBELLE_POSTE[part.poste];
  return (
    <li className="flex flex-wrap items-baseline gap-x-2">
      <span
        aria-hidden="true"
        className="h-2 w-2 shrink-0 rounded-xs"
        style={{ backgroundColor: TONE_VAR[TONE_POSTE[part.poste]] }}
      />
      {/* `min-w-0` sur les deux niveaux : sans lui, `truncate` ne coupe pas dans un conteneur
          flex et le libellé pousserait les chiffres hors du panneau. */}
      <Tooltip content={DESCRIPTION_POSTE[part.poste]} className="min-w-0 flex-1">
        <span className="min-w-0 flex-1 truncate text-2xs text-text-2">{libelle}</span>
      </Tooltip>
      <span className="shrink-0 font-mono text-2xs tabular-nums text-text">
        {formaterTokens(part.tokens)}
      </span>
      {/* Colonne de largeur fixe : le pourcentage ne déplace jamais le reste de la ligne. */}
      <span className="w-12 shrink-0 text-right font-mono text-2xs tabular-nums text-text-2 lg:w-14">
        {formaterPart(part.part)}
      </span>
      {/* Sans survol, la description du poste ne peut pas rester dans la seule infobulle. */}
      <span className="w-full break-words pl-4 text-2xs leading-snug text-text-3 lg:hidden">
        {DESCRIPTION_POSTE[part.poste]}
      </span>
    </li>
  );
}

export interface BarreContexteProps {
  postes: readonly PartContexte[];
  /** Tokens au-delà de la fenêtre. Au-dessus de zéro, les segments débordent et sont rognés. */
  depassement: number;
}

export function BarreContexte({ postes, depassement }: BarreContexteProps): ReactElement {
  return (
    <div className="min-w-0 space-y-2">
      <div
        className="flex h-2 w-full overflow-hidden rounded-xs bg-surface-2"
        style={depassement > 0 ? { boxShadow: CADRE_DEPASSEMENT } : undefined}
      >
        {postes.map((part) => (
          <Segment key={part.poste} part={part} />
        ))}
      </div>
      <ul className="space-y-1">
        {postes.map((part) => (
          <Ligne key={part.poste} part={part} />
        ))}
      </ul>
    </div>
  );
}
