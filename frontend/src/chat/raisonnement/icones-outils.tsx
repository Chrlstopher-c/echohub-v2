/*
 * Icônes des cartes d'outil — monochromes, trait 1,5 px, comme toutes celles du projet (DESIGN.md).
 *
 * Une icône par FAMILLE de geste, pas par outil : lire et présenter partagent le document, écrire
 * et modifier partagent le crayon. Dix dessins distincts pour dix outils seraient dix formes à
 * apprendre ; six gestes se reconnaissent sans légende.
 */

import type { ReactElement } from 'react';
import type { IconeOutil } from './lecture-appel';

const TRAIT = {
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const;

const DESSINS: Readonly<Record<IconeOutil, ReactElement>> = {
  loupe: (
    <>
      <circle cx="7" cy="7" r="4" {...TRAIT} fill="none" />
      <path d="m10 10 3.5 3.5" {...TRAIT} />
    </>
  ),
  globe: (
    <>
      <circle cx="8" cy="8" r="5.5" {...TRAIT} fill="none" />
      <path d="M2.5 8h11M8 2.5c-3.6 3.4-3.6 7.6 0 11M8 2.5c3.6 3.4 3.6 7.6 0 11" {...TRAIT} fill="none" />
    </>
  ),
  document: (
    <>
      <path d="M4 2.5h5.5L12 5v8.5H4z" {...TRAIT} fill="none" />
      <path d="M6 7.5h4M6 10h4" {...TRAIT} />
    </>
  ),
  crayon: <path d="m3 13 .8-3.2 7-7a1.55 1.55 0 0 1 2.2 2.2l-7 7zM9.6 4l2.2 2.2" {...TRAIT} fill="none" />,
  dossier: <path d="M2.5 4.5h4l1.5 1.5h5.5v7h-11z" {...TRAIT} fill="none" />,
  terminal: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" {...TRAIT} fill="none" />
      <path d="m4.5 6.5 2 2-2 2M8.5 10.5h3" {...TRAIT} fill="none" />
    </>
  ),
  code: <path d="m5.5 5-3 3 3 3M10.5 5l3 3-3 3" {...TRAIT} fill="none" />,
  cadre: (
    <>
      <rect x="2.5" y="3" width="11" height="10" rx="1.5" {...TRAIT} fill="none" />
      <path d="M2.5 6h11" {...TRAIT} />
    </>
  ),
  outil: <path d="M6 2.5H3.5v11H6M10 2.5h2.5v11H10" {...TRAIT} fill="none" />,
};

export interface IconeOutilProps {
  readonly icone: IconeOutil;
}

export function IconeDeCarte({ icone }: IconeOutilProps): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" fill="none" aria-hidden="true">
      {DESSINS[icone]}
    </svg>
  );
}
