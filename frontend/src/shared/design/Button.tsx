import type { ButtonHTMLAttributes, ReactElement } from 'react';
import { cn } from './cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Action en cours : le bouton reste en place, affiche l'activité, refuse les clics. */
  loading?: boolean;
}

const BASE =
  'inline-flex items-center justify-center gap-1.5 font-medium rounded-sm select-none ' +
  'transition-colors duration-fast ease-out focus-visible:outline-none ' +
  'focus-visible:shadow-[0_0_0_3px_var(--ring)] disabled:opacity-45 disabled:pointer-events-none';

/* Le danger est réservé aux actions destructrices (éjecter un modèle, supprimer). */
const VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-on-accent hover:bg-accent-hover',
  secondary: 'bg-surface-2 text-text border border-border hover:border-border-strong',
  ghost: 'bg-transparent text-text-2 hover:text-text hover:bg-surface-2',
  danger: 'bg-critical-soft text-critical hover:bg-critical hover:text-on-accent',
};

const SIZE: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-xs',
  md: 'h-8 px-3.5 text-sm',
};

function Spinner(): ReactElement {
  return (
    <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path
        d="M14.5 8a6.5 6.5 0 0 0-6.5-6.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  disabled = false,
  className,
  children,
  ...rest
}: ButtonProps): ReactElement {
  return (
    <button
      type="button"
      className={cn(BASE, VARIANT[variant], SIZE[size], className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}
