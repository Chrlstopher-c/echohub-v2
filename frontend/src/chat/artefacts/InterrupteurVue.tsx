import type { ReactElement } from 'react';
import { cn, Tooltip } from '../../shared/design';
import { IconeApercu, IconeCode } from './icones';

export type VueArtefact = 'code' | 'apercu';

export interface InterrupteurVueProps {
  vue: VueArtefact;
  onChanger: (vue: VueArtefact) => void;
  apercuPossible: boolean;
  raisonAbsenceApercu: string;
}

const CLASSE_BASE =
  'flex h-6 w-6 items-center justify-center rounded-xs transition-colors duration-fast';

function classeBouton(actif: boolean): string {
  return cn(CLASSE_BASE, actif ? 'bg-surface-2 text-text' : 'text-text-3 hover:text-text-2');
}

/**
 * Deux icônes, jamais un menu : code source d'un côté, aperçu de l'autre (plan d'exécution, 2.6).
 *
 * Quand l'aperçu n'a pas de sens pour ce langage, le bouton reste PRÉSENT — retiré, il se lirait
 * comme un bug plutôt que comme une décision. Il n'a volontairement pas l'attribut `disabled` :
 * un bouton HTML désactivé n'émet plus d'événement `mouseenter`, et `Tooltip` (survol) ne
 * s'afficherait jamais. La désactivation est donc simulée — `aria-disabled`, clic ignoré, style
 * atténué — pour que la raison reste lisible au survol, comme l'exige la règle de l'opérateur.
 */
export function InterrupteurVue({
  vue,
  onChanger,
  apercuPossible,
  raisonAbsenceApercu,
}: InterrupteurVueProps): ReactElement {
  const boutonApercu = (
    <button
      type="button"
      aria-pressed={vue === 'apercu'}
      aria-disabled={!apercuPossible}
      data-testid="interrupteur-apercu"
      onClick={() => apercuPossible && onChanger('apercu')}
      className={cn(classeBouton(vue === 'apercu'), !apercuPossible && 'cursor-not-allowed opacity-40')}
    >
      <IconeApercu />
    </button>
  );
  return (
    <div className="flex items-center gap-0.5 rounded-sm border border-border p-0.5">
      <button
        type="button"
        aria-pressed={vue === 'code'}
        data-testid="interrupteur-code"
        onClick={() => onChanger('code')}
        className={classeBouton(vue === 'code')}
      >
        <IconeCode />
      </button>
      {apercuPossible ? boutonApercu : <Tooltip content={raisonAbsenceApercu}>{boutonApercu}</Tooltip>}
    </div>
  );
}
