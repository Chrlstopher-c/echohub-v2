import type { ReactElement } from 'react';
import { Badge, Tooltip } from '../../shared/design';
import type { Capacite, CapaciteDeduite } from '../api/types';
import { definitionCapacite, libelleCapacite, provenance, type CarteCapacites } from './capacites';

/*
 * Capacités d'un dépôt, affichées sur sa carte de résultat.
 *
 * Trois règles reprises telles quelles de la doctrine du domaine :
 *
 * - Trait tireté partout : c'est la marque visuelle de « déduit ». Les mesures du produit — poids
 *   des variantes, verdict de faisabilité — se composent en trait plein, la confusion est donc
 *   impossible à l'œil, sans qu'un mot ait à être lu.
 * - L'infobulle porte la provenance complète. Un badge qui annonce « Vision » sans montrer
 *   l'étiquette ou le fichier qui l'a fait conclure serait exactement l'oracle que la v2 supprime.
 * - Une liste vide n'affiche RIEN. Écrire « aucune capacité » transformerait un silence du dépôt
 *   en affirmation sur le modèle.
 */

/** Au-delà, la ligne cesse d'être lisible d'un coup d'œil ; le reste est compté, comme les variantes. */
const CAPACITES_VISIBLES = 4;

function Justification({ deduite, carte }: { deduite: CapaciteDeduite; carte: CarteCapacites }): ReactElement {
  const texte = definitionCapacite(carte, deduite.capacite);
  return (
    <span className="block space-y-1 leading-relaxed">
      <span className="block font-medium">Déduit d'une déclaration du dépôt, jamais vérifié</span>
      {texte !== null && <span className="block text-text-2">{texte}</span>}
      <span className="block">
        {provenance(deduite.indices).map((ligne) => (
          <span key={ligne} className="block font-mono text-text-3">
            {ligne}
          </span>
        ))}
      </span>
    </span>
  );
}

function BadgeCapacite({
  deduite,
  carte,
  exigee,
}: {
  deduite: CapaciteDeduite;
  carte: CarteCapacites;
  /** Capacité présente dans le filtre actif : l'accent relie le résultat à la puce cochée. */
  exigee: boolean;
}): ReactElement {
  return (
    <Tooltip content={<Justification deduite={deduite} carte={carte} />}>
      <Badge
        tone={exigee ? 'accent' : 'neutral'}
        className={exigee ? 'border border-dashed border-accent' : 'border border-dashed border-border'}
      >
        {libelleCapacite(carte, deduite.capacite)}
      </Badge>
    </Tooltip>
  );
}

export interface CapacitesDeduitesProps {
  /** Dans l'ordre publié par le backend — l'interface ne retrie pas ce vocabulaire. */
  deduites: readonly CapaciteDeduite[];
  carte: CarteCapacites;
  exigees: readonly Capacite[];
}

export function CapacitesDeduites({ deduites, carte, exigees }: CapacitesDeduitesProps): ReactElement | null {
  if (deduites.length === 0) {
    return null;
  }
  const visibles = deduites.slice(0, CAPACITES_VISIBLES);
  const restantes = deduites.length - visibles.length;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-2xs text-text-3">Déduit</span>
      {visibles.map((deduite) => (
        <BadgeCapacite
          key={deduite.capacite}
          deduite={deduite}
          carte={carte}
          exigee={exigees.includes(deduite.capacite)}
        />
      ))}
      {restantes > 0 && <span className="text-2xs text-text-3">+{restantes}</span>}
    </div>
  );
}
