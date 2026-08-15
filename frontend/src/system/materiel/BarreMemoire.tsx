import type { ReactElement } from 'react';
import { enGo } from '../format';
import type { JaugeMesuree } from './echelle';

/*
 * Une ressource physique, une barre, à l'échelle réelle.
 *
 * La zone occupée ouvre la barre en hachures neutres : elle est MONTRÉE, jamais soustraite en
 * silence du total annoncé. Sur la machine cible, c'est ce qui rend visible le gigaoctet et demi
 * que le bureau Windows retient avant même qu'un modèle soit chargé.
 */

export type ToneMemoire = 'vram' | 'ram';

export interface BarreMemoireProps {
  libelle: string;
  jauge: JaugeMesuree;
  tone: ToneMemoire;
  /** Ce qui occupe la ressource, formulé sans l'attribuer à un coupable qu'on n'a pas mesuré. */
  legende: string;
}

const REMPLISSAGE: Record<ToneMemoire, string> = {
  vram: 'bg-mem-vram',
  ram: 'bg-mem-ram',
};

const TEXTE: Record<ToneMemoire, string> = {
  vram: 'text-mem-vram',
  ram: 'text-mem-ram',
};

export function BarreMemoire({ libelle, jauge, tone, legende }: BarreMemoireProps): ReactElement {
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-xs text-text-2">{libelle}</span>
        <span className="whitespace-nowrap font-mono text-xs tabular-nums text-text">
          <span className={TEXTE[tone]}>{enGo(jauge.libreOctets)}</span>
          {` / ${enGo(jauge.totalOctets)} Go libres`}
        </span>
      </div>

      {/* Le conteneur porte l'échelle commune : la barre n'occupe qu'une part de sa largeur. */}
      <div className="h-2.5 w-full">
        <div
          className="flex h-full overflow-hidden rounded-xs bg-surface-2 transition-[width] duration-base ease-linear"
          style={{ width: `${jauge.largeurPct.toFixed(2)}%` }}
        >
          <div
            className="eh-hatched h-full shrink-0 transition-[width] duration-base ease-linear"
            style={{ width: `${jauge.occupePct.toFixed(2)}%` }}
            aria-hidden="true"
          />
          <div className={`h-full grow ${REMPLISSAGE[tone]}`} aria-hidden="true" />
        </div>
      </div>

      <p className="mt-1 text-2xs text-text-3">
        {legende} : <span className="font-mono tabular-nums">{enGo(jauge.occupeOctets)} Go</span>
      </p>
    </div>
  );
}
