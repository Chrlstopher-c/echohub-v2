import type { ReactElement } from 'react';
import { Badge, Button } from '../../shared/design';
import type { CleReglage } from './contrat';
import { LIBELLES } from './definitions';
import type { EtatEnregistrement } from './useReglagesConversation';

/*
 * État d'enregistrement, dit sans arrondi.
 *
 * Le mot compte autant que la couleur : « à jour » affirme que l'affiché est ce que le backend a
 * retenu, « modifié » avoue l'inverse. Une pastille verte posée en permanence — le réflexe des
 * formulaires qui s'enregistrent seuls — ferait exactement la promesse que ce panneau ne peut pas
 * tenir tant que la requête n'est pas revenue.
 *
 * L'échec est ambre et non rouge : il est récupérable, l'ambre est la famille du compromis dans
 * DESIGN.md, et le rouge y est réservé à ce qui ne repartira pas tout seul. Il nomme sa raison (le
 * message et la remédiation du backend) et les champs concernés, parce qu'une valeur refusée doit
 * pouvoir être retrouvée à l'écran sans chercher.
 */

export function BadgeEnregistrement({ etat }: { etat: EtatEnregistrement }): ReactElement {
  if (etat.type === 'en_cours') {
    return (
      <Badge tone="accent" dot pulse>
        enregistrement
      </Badge>
    );
  }
  if (etat.type === 'differe') {
    return (
      <Badge tone="neutral" dot>
        modifié
      </Badge>
    );
  }
  if (etat.type === 'echoue') {
    return <Badge tone="caution">non enregistré</Badge>;
  }
  return (
    <Badge tone="ok" dot>
      à jour
    </Badge>
  );
}

export interface EchecEnregistrementProps {
  readonly etat: EtatEnregistrement;
  readonly modifies: readonly CleReglage[];
  readonly onReessayer: () => void;
}

export function EchecEnregistrement({ etat, modifies, onReessayer }: EchecEnregistrementProps): ReactElement | null {
  if (etat.type !== 'echoue') {
    return null;
  }
  const champs = modifies.map((cle) => LIBELLES[cle]).join(', ');
  return (
    <div className="space-y-1.5 rounded-sm border border-caution bg-caution-soft px-3 py-2">
      <p className="text-xs text-caution">{etat.raison}</p>
      {champs !== '' && (
        <p className="text-2xs text-text-2">
          Reste affiché mais non enregistré : <span className="text-text">{champs}</span>.
        </p>
      )}
      <Button variant="secondary" size="sm" onClick={onReessayer}>
        Réessayer
      </Button>
    </div>
  );
}
