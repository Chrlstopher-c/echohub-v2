import type { ReactElement } from 'react';
import { Badge, Tooltip, cn } from '../../shared/design';
import type { Capacite, DefinitionCapacite } from '../api/types';
import type { VocabulaireCapacites } from './useDefinitionsCapacites';

/*
 * Filtres de capacités — sélection multiple, combinée en ET par le backend.
 *
 * Deux choix portent tout le composant :
 *
 * 1. La liste des puces vient de `GET /models/capacites`, pas d'une constante locale. Si l'appel
 *    échoue, aucune puce n'est proposée : filtrer sur un vocabulaire deviné ferait porter au
 *    backend un filtre que l'interface aurait inventé.
 * 2. Le trait tireté n'est pas décoratif — c'est le mot visuel de « déduit ». Il se retrouve à
 *    l'identique sur les badges des résultats, si bien qu'une capacité ne peut jamais être
 *    confondue avec une mesure, qui se compose toujours en trait plein.
 */

function PuceCapacite({
  definition,
  actif,
  onBasculer,
}: {
  definition: DefinitionCapacite;
  actif: boolean;
  onBasculer: () => void;
}): ReactElement {
  return (
    <Tooltip content={<span className="block leading-relaxed">{definition.definition}</span>}>
      <button
        type="button"
        onClick={onBasculer}
        aria-pressed={actif}
        className={cn(
          'h-7 rounded-xs border border-dashed px-2.5 text-xs font-medium',
          'transition-colors duration-fast ease-out outline-none',
          'focus-visible:shadow-[0_0_0_3px_var(--ring)]',
          actif
            ? 'border-accent bg-accent-soft text-accent'
            : 'border-border bg-surface-2 text-text-2 hover:text-text',
        )}
      >
        {definition.libelle}
      </button>
    </Tooltip>
  );
}

/** Compte des filtres actifs et effacement immédiat — visibles seulement quand ils ont un sens. */
function EnTeteFiltre({ actives, onEffacer }: { actives: number; onEffacer: () => void }): ReactElement {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-2xs text-text-3">
        Capacités déduites — annoncées par le dépôt, jamais vérifiées dans le modèle
      </span>
      {actives > 0 && (
        <>
          <Badge tone="accent">
            <span className="font-mono tabular-nums">{actives}</span>
            {actives > 1 ? ' filtres actifs' : ' filtre actif'}
          </Badge>
          <button
            type="button"
            onClick={onEffacer}
            className={cn(
              'rounded-xs px-1 text-2xs text-text-2 outline-none',
              'transition-colors duration-fast ease-out hover:text-text',
              'focus-visible:shadow-[0_0_0_3px_var(--ring)]',
            )}
          >
            Tout effacer
          </button>
        </>
      )}
    </div>
  );
}

export interface FiltreCapacitesProps {
  vocabulaire: VocabulaireCapacites;
  selection: readonly Capacite[];
  onBasculer: (capacite: Capacite) => void;
  onEffacer: () => void;
}

export function FiltreCapacites({
  vocabulaire,
  selection,
  onBasculer,
  onEffacer,
}: FiltreCapacitesProps): ReactElement | null {
  if (vocabulaire.erreur !== null) {
    return (
      <p className="rounded-xs bg-caution-soft px-2 py-1.5 text-2xs text-caution">
        Filtres de capacités indisponibles — {vocabulaire.erreur} Aucune capacité n'est proposée tant
        que la liste qui filtre réellement n'a pas été lue.
      </p>
    );
  }
  // Vocabulaire pas encore arrivé : rien à proposer, et surtout rien à inventer en attendant.
  if (vocabulaire.definitions.length === 0) {
    return null;
  }
  return (
    <div className="space-y-1.5">
      <EnTeteFiltre actives={selection.length} onEffacer={onEffacer} />
      <div className="flex flex-wrap items-center gap-1.5">
        {vocabulaire.definitions.map((definition) => (
          <PuceCapacite
            key={definition.capacite}
            definition={definition}
            actif={selection.includes(definition.capacite)}
            onBasculer={(): void => onBasculer(definition.capacite)}
          />
        ))}
      </div>
    </div>
  );
}
