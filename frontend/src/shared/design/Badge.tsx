import type { CSSProperties, ReactElement, ReactNode } from 'react';
import { cn } from './cn';
import { TONE_SOFT_VAR, TONE_VAR, type Tone } from './tones';

export interface BadgeProps {
  tone?: Tone;
  /** Point d'état devant le texte (état d'un modèle, d'un moteur). */
  dot?: boolean;
  /** Pouls sur le point : réservé à une activité réellement en cours (génération, chargement). */
  pulse?: boolean;
  className?: string;
  children: ReactNode;
}

export function Badge({
  tone = 'neutral',
  dot = false,
  pulse = false,
  className,
  children,
}: BadgeProps): ReactElement {
  // Couleurs par variable CSS : le badge suit le thème sans logique supplémentaire.
  const style: CSSProperties = { color: TONE_VAR[tone], backgroundColor: TONE_SOFT_VAR[tone] };
  return (
    <span
      style={style}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-xs px-1.5 py-0.5 text-2xs font-medium',
        className,
      )}
    >
      {(dot || pulse) && (
        <span
          aria-hidden="true"
          className={cn('h-1.5 w-1.5 rounded-full bg-current', pulse && 'animate-eh-pulse')}
        />
      )}
      {children}
    </span>
  );
}
