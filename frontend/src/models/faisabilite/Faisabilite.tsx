import type { ReactElement } from 'react';
import { Badge, Tooltip, type Tone } from '../../shared/design';
import { LIBELLE_VERDICT, RESERVE, type Faisabilite, type Verdict } from './evaluation';

/*
 * Rendu du verdict de faisabilité.
 *
 * Le vocabulaire de couleur est celui de la mémoire, pas celui du succès : cyan quand les octets
 * résident en VRAM, sable quand une partie reste en RAM — le sable EST le compromis, et il est
 * enfant de la famille ambre pour cette raison. Rouge seulement quand rien ne rentre.
 *
 * L'infobulle porte les opérandes de la comparaison. Un verdict sans ses chiffres serait un oracle.
 */

const TON: Record<Verdict, Tone> = {
  tient_vram: 'vram',
  deborde_ram: 'ram',
  ne_tient_pas: 'critical',
  indeterminee: 'neutral',
};

export interface PastilleFaisabiliteProps {
  faisabilite: Faisabilite;
  /** Compacte la pastille pour une liste dense (choix de quantification). */
  compacte?: boolean;
}

export function PastilleFaisabilite({ faisabilite, compacte = false }: PastilleFaisabiliteProps): ReactElement {
  return (
    <Tooltip
      content={
        <span>
          <span className="font-mono tabular-nums">{faisabilite.comparaison}</span>
          <span className="mt-1 block text-text-2">{RESERVE}</span>
        </span>
      }
    >
      <Badge tone={TON[faisabilite.verdict]} dot={!compacte}>
        {LIBELLE_VERDICT[faisabilite.verdict]}
      </Badge>
    </Tooltip>
  );
}

/** Réserve rappelée une fois par écran : le verdict est une comparaison, pas un plan. */
export function BandeauReserve(): ReactElement {
  return <p className="text-2xs leading-relaxed text-text-3">{RESERVE}</p>;
}
