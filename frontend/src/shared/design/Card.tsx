import type { ReactElement, ReactNode } from 'react';
import { cn } from './cn';

export type CardLevel = 'surface' | 'raised' | 'overlay';

export interface CardProps {
  /** Niveau d'élévation — un enfant n'est jamais plus élevé que son parent. */
  level?: CardLevel;
  title?: string;
  /** Zone d'actions du header (boutons, badge d'état). */
  actions?: ReactNode;
  padding?: 'none' | 'sm' | 'md';
  className?: string;
  children: ReactNode;
}

const LEVEL: Record<CardLevel, string> = {
  surface: 'bg-surface border border-border',
  raised: 'bg-surface-2 border border-border',
  overlay: 'bg-overlay border border-border-strong shadow-2',
};

const PADDING: Record<NonNullable<CardProps['padding']>, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
};

export function Card({
  level = 'surface',
  title,
  actions,
  padding = 'md',
  className,
  children,
}: CardProps): ReactElement {
  return (
    <section className={cn('rounded-md', LEVEL[level], PADDING[padding], className)}>
      {(title !== undefined || actions !== undefined) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {title !== undefined && <h2 className="text-md font-semibold text-text">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
