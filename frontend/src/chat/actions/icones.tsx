/*
 * Icônes des actions de message. Monochromes, trait 1,5 px, grille 16 : la règle iconographique de
 * DESIGN.md. Elles portent `aria-hidden` — le sens est dans le `aria-label` du bouton, pas ici.
 */

import type { ReactElement, ReactNode } from 'react';

const TAILLE = 'h-3.5 w-3.5';

interface TraceProps {
  d: string;
}

function Trace({ d }: TraceProps): ReactElement {
  return <path d={d} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />;
}

interface CadreProps {
  children: ReactNode;
}

function Cadre({ children }: CadreProps): ReactElement {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={TAILLE}>
      {children}
    </svg>
  );
}

export function IconeCopier(): ReactElement {
  return (
    <Cadre>
      <rect x="6" y="4" width="8" height="8" rx="1.75" stroke="currentColor" strokeWidth="1.5" />
      <Trace d="M10 4v-.25A1.75 1.75 0 0 0 8.25 2h-4.5A1.75 1.75 0 0 0 2 3.75v4.5A1.75 1.75 0 0 0 3.75 10H4" />
    </Cadre>
  );
}

export function IconeCoche(): ReactElement {
  return (
    <Cadre>
      <Trace d="M3 8.4 6.2 11.6 13 4.8" />
    </Cadre>
  );
}

export function IconeEditer(): ReactElement {
  return (
    <Cadre>
      <Trace d="M11.1 2.9a1.6 1.6 0 0 1 2.3 2.3L6.6 12H4.3V9.7l6.8-6.8Z" />
    </Cadre>
  );
}

export function IconeRejouer(): ReactElement {
  return (
    <Cadre>
      <Trace d="M13 8a5 5 0 1 1-1.7-3.75" />
      <Trace d="M13.2 2.6v2.7h-2.7" />
    </Cadre>
  );
}

export function IconeChevronGauche(): ReactElement {
  return (
    <Cadre>
      <Trace d="M9.75 3.5 5.25 8l4.5 4.5" />
    </Cadre>
  );
}

export function IconeChevronDroite(): ReactElement {
  return (
    <Cadre>
      <Trace d="M6.25 3.5 10.75 8l-4.5 4.5" />
    </Cadre>
  );
}
