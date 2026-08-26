/*
 * Entête de la colonne d'échange.
 *
 * Elle porte les deux seuls chemins d'ouverture des tiroirs sous 1024 px. Ils sont visibles en
 * permanence et jamais remplacés par un geste de bord : un geste que rien n'annonce est une action
 * absente. Au-dessus du seuil les colonnes sont en flux, les boutons disparaissent.
 */

import type { ReactElement } from 'react';
import { Badge, Button } from '../shared/design';

export interface EnTeteChatProps {
  readonly titre: string;
  readonly modele: string | null;
  readonly pret: boolean;
  readonly onReglages: () => void;
  readonly onOutils: () => void;
  readonly onOuvrirConversations: () => void;
  readonly onOuvrirPlan: () => void;
}

function IconeListe(): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden="true">
      <path d="M2.5 4h11M2.5 8h11M2.5 12h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function IconePlan(): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden="true">
      <path
        d="M2.5 12.5v-3M6.5 12.5v-6M10.5 12.5v-9M14 12.5H2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ActionsEntete({ pret, onOutils, onReglages, onOuvrirPlan }: Pick<
  EnTeteChatProps,
  'pret' | 'onOutils' | 'onReglages' | 'onOuvrirPlan'
>): ReactElement {
  return (
    <div className="flex shrink-0 items-center gap-1 lg:gap-2">
      <Badge tone={pret ? 'ok' : 'neutral'} dot>
        {pret ? 'moteur prêt' : 'moteur inactif'}
      </Badge>
      {/* « Outils » vit à côté de « Réglages » : les deux disent ce que la conversation met à
          disposition du modèle — l'un les capacités, l'autre les paramètres. */}
      <Button variant="ghost" size="sm" onClick={onOutils}>
        Outils
      </Button>
      <Button variant="ghost" size="sm" onClick={onReglages}>
        Réglages
      </Button>
      <Button variant="ghost" size="sm" className="lg:hidden" aria-label="Plan de chargement" onClick={onOuvrirPlan}>
        <IconePlan />
      </Button>
    </div>
  );
}

export function EnTeteChat(props: EnTeteChatProps): ReactElement {
  const { titre, modele } = props;
  return (
    <header className="flex shrink-0 items-center gap-2 border-b border-border px-2 py-2 lg:gap-3 lg:px-6 lg:py-3">
      <Button
        variant="ghost"
        size="sm"
        className="lg:hidden"
        aria-label="Conversations"
        onClick={props.onOuvrirConversations}
      >
        <IconeListe />
      </Button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-md font-semibold text-text">{titre}</h1>
        {modele !== null && <p className="truncate text-2xs text-text-3">{modele}</p>}
      </div>
      <ActionsEntete
        pret={props.pret}
        onOutils={props.onOutils}
        onReglages={props.onReglages}
        onOuvrirPlan={props.onOuvrirPlan}
      />
    </header>
  );
}
