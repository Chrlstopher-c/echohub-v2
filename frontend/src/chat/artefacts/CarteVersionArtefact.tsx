/*
 * Carte d'un artefact créé, à l'endroit du fil où le modèle l'a produit.
 *
 * Même grammaire que `CarteOutil` — un artefact EST le résultat d'un appel d'outil, il ne forme
 * pas un troisième langage visuel — mais son geste diffère : la carte ne se déplie pas, elle OUVRE
 * l'atelier. Le contenu se regarde dans le panneau, pas dans le fil ; la carte n'est que la poignée
 * qui y mène, et reste marquée tant que son artefact est celui qui est ouvert.
 */

import type { ReactElement } from 'react';
import { cn } from '../../shared/design';
import type { VersionArtefact } from './detection';
import { useCapacitesAtelier } from './fournisseur-atelier';

const LIBELLE_TYPE: Readonly<Record<string, string>> = {
  html: 'page',
  markdown: 'document',
  code: 'code',
  svg: 'image',
  mermaid: 'diagramme',
  inconnu: 'texte',
};

function IconeCadre(): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" fill="none" aria-hidden="true">
      <rect x="2.5" y="3" width="11" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M2.5 6h11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export interface CarteVersionArtefactProps {
  readonly version: VersionArtefact;
}

export function CarteVersionArtefact({ version }: CarteVersionArtefactProps): ReactElement {
  const atelier = useCapacitesAtelier();
  const active = atelier?.artefactOuvert === version.artefact_id;
  return (
    <button
      type="button"
      onClick={() => atelier?.ouvrirVersion(version)}
      disabled={atelier === null}
      data-testid="carte-version-artefact"
      className={cn(
        'flex w-full min-h-[44px] max-w-full items-center gap-x-2 rounded-sm px-2.5 py-2 text-left',
        'transition-colors duration-fast ease-out lg:min-h-0 lg:py-1.5',
        'focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--ring)]',
        active ? 'bg-surface-2' : 'bg-surface hover:bg-surface-2',
      )}
    >
      <span className={active ? 'text-accent' : 'text-text-3'}>
        <IconeCadre />
      </span>
      <span className="shrink-0 text-xs font-medium text-text-2">Artefact</span>
      <span className="min-w-0 flex-1 truncate text-xs text-text" title={version.titre}>
        {version.titre}
      </span>
      <span className="shrink-0 text-2xs text-text-3">{LIBELLE_TYPE[version.type] ?? 'texte'}</span>
      <span className="shrink-0 font-mono text-2xs tabular-nums text-text-3">v{version.version}</span>
    </button>
  );
}
