import type { ChangeEvent, ReactElement } from 'react';
import { cn } from './cn';
import { TONE_SOFT_VAR, TONE_VAR, type Tone } from './tones';

/*
 * Slider à zones sémantiques. Cas d'usage central : la taille de contexte, dont
 * certaines plages coûtent la moitié du débit mesuré (41 → 19,6 tok/s). La zone
 * teinte le rail ; la valeur et le remplissage adoptent le ton de la zone où l'on est.
 */

export interface SliderZone {
  /** Début de la zone, en unités de la valeur (inclus, jusqu'à la zone suivante ou max). */
  from: number;
  tone: 'caution' | 'critical';
}

export interface SliderProps {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  label?: string;
  /** Rendu de la valeur — ex. « 57 344 tokens ». Affiché en mono. */
  format?: (value: number) => string;
  zones?: readonly SliderZone[];
  disabled?: boolean;
  id?: string;
}

function pct(value: number, min: number, max: number): number {
  if (max <= min) {
    return 0;
  }
  return Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100));
}

function activeTone(value: number, zones: readonly SliderZone[]): Tone {
  // La dernière zone franchie donne le ton ; hors zone, l'accent (valeur saine).
  let tone: Tone = 'accent';
  for (const zone of zones) {
    if (value >= zone.from) {
      tone = zone.tone;
    }
  }
  return tone;
}

function ZoneSegments({ zones, min, max }: Pick<SliderProps, 'min' | 'max'> & {
  zones: readonly SliderZone[];
}): ReactElement {
  return (
    <>
      {zones.map((zone, i) => {
        const next = zones[i + 1];
        const left = pct(zone.from, min, max);
        const right = next !== undefined ? pct(next.from, min, max) : 100;
        return (
          <span
            key={zone.from}
            aria-hidden="true"
            className="absolute top-0 h-full"
            style={{
              left: `${left}%`,
              width: `${right - left}%`,
              backgroundColor: TONE_SOFT_VAR[zone.tone],
            }}
          />
        );
      })}
    </>
  );
}

function SliderHeader({ label, format, value, tone, id }: Pick<SliderProps, 'label' | 'format' | 'id'> & {
  value: number;
  tone: Tone;
}): ReactElement | null {
  if (label === undefined && format === undefined) {
    return null;
  }
  return (
    <div className="mb-1.5 flex items-baseline justify-between gap-2">
      {label !== undefined && (
        <label htmlFor={id} className="text-xs text-text-2">
          {label}
        </label>
      )}
      {format !== undefined && (
        <span className="font-mono text-xs tabular-nums" style={{ color: TONE_VAR[tone] }}>
          {format(value)}
        </span>
      )}
    </div>
  );
}

export function Slider({
  value,
  min,
  max,
  step = 1,
  onChange,
  label,
  format,
  zones = [],
  disabled = false,
  id,
}: SliderProps): ReactElement {
  const tone = activeTone(value, zones);
  const handleChange = (e: ChangeEvent<HTMLInputElement>): void => onChange(Number(e.target.value));
  return (
    <div className={cn(disabled && 'opacity-45')}>
      <SliderHeader label={label} format={format} value={value} tone={tone} id={id} />
      {/* Le rail garde son épaisseur ; c'est la zone d'appui de l'input, en surimpression, qui
          monte à 44 px au doigt — épaissir le rail lui-même déformerait la lecture des zones. */}
      <div className="relative flex h-11 items-center lg:h-3.5">
        <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
          <ZoneSegments zones={zones} min={min} max={max} />
          <span
            aria-hidden="true"
            className="absolute top-0 h-full rounded-full transition-colors duration-fast"
            style={{ width: `${pct(value, min, max)}%`, backgroundColor: TONE_VAR[tone] }}
          />
        </div>
        <input
          id={id}
          type="range"
          className="eh-range absolute inset-0"
          value={value}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onChange={handleChange}
          aria-label={label}
        />
      </div>
    </div>
  );
}
