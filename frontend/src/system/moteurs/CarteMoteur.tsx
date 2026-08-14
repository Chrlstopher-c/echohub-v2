import type { ReactElement, ReactNode } from 'react';
import { Badge, Button, Card, type Tone } from '../../shared/design';
import type { SanteMoteur, StatutMoteur } from '../api/types';
import { heure } from '../format';

/*
 * Santé d'un moteur.
 *
 * Un seul champ porte l'état — `statut` — et les couleurs suivent la sémantique du design :
 * `incomplet` est ambre parce qu'une réinstallation le répare, `defaillant` est rouge parce que le
 * binaire est là et ne marche pas. La v1 avait deux booléens indépendants qui se contredisaient.
 */

const LIBELLE_STATUT: Record<StatutMoteur, string> = {
  absent: 'absent',
  incomplet: 'installation interrompue',
  defaillant: 'défaillant',
  fonctionnel: 'fonctionnel',
};

const TON_STATUT: Record<StatutMoteur, Tone> = {
  absent: 'neutral',
  incomplet: 'caution',
  defaillant: 'critical',
  fonctionnel: 'ok',
};

function Architectures({ sante }: { sante: SanteMoteur }): ReactElement {
  if (sante.architectures_gpu.length === 0) {
    return <p className="text-2xs text-text-3">Architectures CUDA non relevées.</p>;
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {sante.architectures_gpu.map((architecture) => (
        <Badge key={architecture} tone="vram">
          {architecture}
        </Badge>
      ))}
      {!sante.couvre_le_parc && <Badge tone="caution">parc incomplet — sm_86 et sm_120 attendus</Badge>}
    </div>
  );
}

function Details({ details }: { details: Record<string, string> }): ReactElement | null {
  const entrees = Object.entries(details);
  if (entrees.length === 0) {
    return null;
  }
  return (
    <dl className="mt-3 space-y-1 border-t border-border pt-3">
      {entrees.map(([cle, valeur]) => (
        <div key={cle} className="flex items-baseline justify-between gap-3">
          <dt className="shrink-0 text-2xs text-text-3">{cle}</dt>
          <dd className="min-w-0 truncate text-right font-mono text-2xs tabular-nums text-text-2" title={valeur}>
            {valeur}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export interface CarteMoteurProps {
  titre: string;
  sante: SanteMoteur;
  /** Action de sondage, quand le moteur en propose une. */
  onSonder?: () => void;
  sondage?: boolean;
  children?: ReactNode;
}

export function CarteMoteur({ titre, sante, onSonder, sondage = false, children }: CarteMoteurProps): ReactElement {
  return (
    <Card
      title={titre}
      actions={
        <div className="flex items-center gap-2">
          <Badge tone={TON_STATUT[sante.statut]} dot>
            {LIBELLE_STATUT[sante.statut]}
          </Badge>
          {onSonder !== undefined && (
            <Button size="sm" variant="ghost" onClick={onSonder} loading={sondage}>
              Sonder
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-2">
        <p className="font-mono text-xs tabular-nums text-text">{sante.version ?? 'version inconnue'}</p>
        <Architectures sante={sante} />
        {sante.diagnostic !== '' && <p className="text-xs text-text-2">{sante.diagnostic}</p>}
        {sante.remediation !== '' && (
          <p className="rounded-xs bg-caution-soft px-2 py-1.5 text-2xs text-caution">{sante.remediation}</p>
        )}
      </div>
      <Details details={sante.details} />
      <p className="mt-3 text-2xs text-text-3">Mesuré à {heure(sante.mesure_le)}</p>
      {children}
    </Card>
  );
}
