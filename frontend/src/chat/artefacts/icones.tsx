/*
 * Icônes de l'interrupteur code/aperçu et de la carte d'artefact. Monochromes, trait 1,5 px,
 * grille 16 — même convention que `chat/actions/icones.tsx`.
 */

import type { ReactElement } from 'react';

const TAILLE = 'h-3.5 w-3.5';

function Cadre({ children }: { children: ReactElement | ReactElement[] }): ReactElement {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={TAILLE}>
      {children}
    </svg>
  );
}

/** Chevrons `< >` — code source. */
export function IconeCode(): ReactElement {
  return (
    <Cadre>
      <path
        d="M6 5 3 8l3 3M10 5l3 3-3 3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Cadre>
  );
}

/** Œil — aperçu rendu. */
export function IconeApercu(): ReactElement {
  return (
    <Cadre>
      <path
        d="M2 8s2.2-3.5 6-3.5S14 8 14 8s-2.2 3.5-6 3.5S2 8 2 8Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.5" />
    </Cadre>
  );
}

/** Feuille cornée — représente un fichier générique dans la carte d'artefact. */
export function IconeFichier(): ReactElement {
  return (
    <Cadre>
      <path
        d="M4.5 2.5h4.5L12 5.5v8a1 1 0 0 1-1 1h-6.5a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M9 2.5V5.5h3" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </Cadre>
  );
}
