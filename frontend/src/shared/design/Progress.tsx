import type { CSSProperties, ReactElement } from 'react';
import { cn } from './cn';
import { TONE_VAR, type Tone } from './tones';

export interface ProgressProps {
  /** Valeur en unités réelles (Go, octets, tokens) — jamais un pourcentage simulé. */
  value: number;
  max: number;
  tone?: Tone;
  label?: string;
  /** Rendu du couple valeur/max — ex. « 8,2 / 14,7 Go ». Affiché en mono. */
  format?: (value: number, max: number) => string;
  className?: string;
}

function clampRatio(value: number, max: number): number {
  if (max <= 0) {
    return 0;
  }
  return Math.min(1, Math.max(0, value / max));
}

/*
 * Barre de progression réelle : la largeur suit la donnée, la transition est
 * linéaire (un travail régulier doit paraître régulier — pas de courbe flatteuse).
 */
export function Progress({
  value,
  max,
  tone = 'accent',
  label,
  format,
  className,
}: ProgressProps): ReactElement {
  const ratio = clampRatio(value, max);
  const fill: CSSProperties = {
    width: `${(ratio * 100).toFixed(2)}%`,
    backgroundColor: TONE_VAR[tone],
  };
  return (
    <div className={className}>
      {(label !== undefined || format !== undefined) && (
        <div className="mb-1 flex items-baseline justify-between gap-2">
          {label !== undefined && <span className="text-xs text-text-2">{label}</span>}
          {format !== undefined && (
            <span className="font-mono text-xs tabular-nums text-text">{format(value, max)}</span>
          )}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-label={label}
        className={cn('h-1.5 w-full overflow-hidden rounded-full bg-surface-2')}
      >
        <div className="h-full rounded-full transition-[width] duration-base ease-linear" style={fill} />
      </div>
    </div>
  );
}
