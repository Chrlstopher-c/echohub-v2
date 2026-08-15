import { LayoutGroup, motion } from 'framer-motion';
import type { ReactElement } from 'react';
import { TONE_VAR, transitionLayout } from '../../shared/design';
import type { PlanDeChargement } from '../api/contrats';

/*
 * Les couches sont des cellules discrètes : autant de cellules que de couches RÉELLES lues dans le
 * GGUF. On compte des couches, on ne lit pas un pourcentage — c'est la différence entre « 28 sur
 * 41 » et « 68 % », et c'est la première chose que la v1 se trompait à estimer (80 pour 41).
 *
 * Quand un plan se replie, les cellules qui quittent le GPU glissent physiquement vers la rangée
 * RAM : même géométrie, même vocabulaire, seul l'état change. Il n'y a pas d'écran d'erreur à part.
 */

const CELLULES_ANIMEES_MAX = 160;

interface RangeeProps {
  titre: string;
  compte: number;
  total: number;
  indices: number[];
  couleur: string;
  anime: boolean;
}

function Rangee({ titre, compte, total, indices, couleur, anime }: RangeeProps): ReactElement {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-xs text-text-2">{titre}</span>
        <span className="font-mono text-xs tabular-nums" style={{ color: couleur }}>
          {compte} / {total}
        </span>
      </div>
      {/* `flex-wrap` : les cellules retombent à la ligne dans un tiroir étroit plutôt que de
          déborder — leur largeur de 6px reste une unité de comptage, pas une mesure de conteneur. */}
      <div className="flex min-h-[0.75rem] min-w-0 flex-wrap gap-[2px]">
        {indices.map((indice) => (
          <motion.span
            key={indice}
            layoutId={anime ? `couche-${indice}` : undefined}
            transition={transitionLayout}
            className="h-3 w-[6px] rounded-[1px]"
            style={{ backgroundColor: couleur }}
          />
        ))}
      </div>
    </div>
  );
}

export interface RubanCouchesProps {
  plan: PlanDeChargement;
}

export function RubanCouches({ plan }: RubanCouchesProps): ReactElement {
  const total = plan.couches_totales;
  // `couches_gpu = -1` signifie « toutes » côté llama.cpp : le ruban le rend explicite.
  const surGpu = plan.couches_gpu.valeur < 0 ? total : Math.min(plan.couches_gpu.valeur, total);
  const indices = Array.from({ length: total }, (_, index) => index);
  // Au-delà de cette taille, l'animation de layout coûte plus qu'elle n'explique.
  const anime = total <= CELLULES_ANIMEES_MAX;
  return (
    <LayoutGroup>
      <div className="min-w-0 space-y-2.5">
        <Rangee
          titre="Couches sur GPU"
          compte={surGpu}
          total={total}
          indices={indices.slice(0, surGpu)}
          couleur={TONE_VAR.vram}
          anime={anime}
        />
        <Rangee
          titre="Couches en RAM"
          compte={total - surGpu}
          total={total}
          indices={indices.slice(surGpu)}
          couleur={TONE_VAR.ram}
          anime={anime}
        />
        <p className="break-words font-mono text-2xs leading-relaxed text-text-3">
          {plan.couches_gpu.justification}
        </p>
      </div>
    </LayoutGroup>
  );
}
