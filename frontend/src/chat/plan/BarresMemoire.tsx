import { motion } from 'framer-motion';
import { useMemo } from 'react';
import type { ReactElement } from 'react';
import { TONE_VAR, Tooltip, cn, transitionLayout, type Tone } from '../../shared/design';
import type { PlanDeChargement, PosteMemoire } from '../api/contrats';
import { formaterOctets } from './format';

/*
 * Une barre par ressource physique, à l'échelle réelle : VRAM et RAM partagent le même nombre de
 * pixels par octet, donc 16 Go de VRAM PARAÎT plus petit que 22 Go de RAM. Une échelle normalisée
 * ferait disparaître la contrainte, qui est précisément le sujet de l'écran.
 *
 * La part de VRAM occupée hors plan (bureau Windows, autres processus) ouvre la barre en zone
 * hachurée : elle est montrée, jamais soustraite en silence.
 */

interface Segment {
  cle: string;
  octets: number;
  tone: Tone;
  libelle: string;
  justification: string;
  hachure: boolean;
}

interface SegmentsPlan {
  vram: Segment[];
  ram: Segment[];
}

/*
 * Correspondance libellé de poste → couleur. Elle suit le vocabulaire du planificateur
 * (`budget.py`) ; tout poste inconnu reste gris plutôt que d'emprunter une couleur qui mentirait.
 */
function tonePoste(libelle: string): Tone {
  const normalise = libelle.toLowerCase();
  if (normalise.includes('cache kv')) {
    return 'kv';
  }
  if (normalise.includes('couches') || normalise.includes('poids')) {
    return 'vram';
  }
  return 'neutral';
}

function segmentPoste(poste: PosteMemoire, index: number): Segment {
  return {
    cle: `poste-${index}`,
    octets: poste.octets,
    tone: tonePoste(poste.libelle),
    libelle: poste.libelle,
    justification: poste.justification,
    hachure: false,
  };
}

function construireSegments(plan: PlanDeChargement, vramTotaleOctets: number): SegmentsPlan {
  const budget = plan.budget;
  const horsPlan = Math.max(0, vramTotaleOctets - budget.vram_disponible_octets);
  const vram: Segment[] = budget.postes.map(segmentPoste);
  if (horsPlan > 0) {
    vram.unshift({
      cle: 'hors-plan',
      octets: horsPlan,
      tone: 'neutral',
      hachure: true,
      libelle: 'Occupé hors plan',
      justification: 'VRAM déjà prise par le bureau et les autres processus au moment de la mesure.',
    });
  }
  const ram: Segment[] = budget.ram_requise_octets === 0 ? [] : [{
    cle: 'ram',
    octets: budget.ram_requise_octets,
    tone: 'ram',
    hachure: false,
    libelle: 'Couches déportées en RAM',
    justification: 'Poids qui ne tiennent pas en VRAM : le CPU les calcule, nettement plus lentement.',
  }];
  return { vram, ram };
}

function SegmentBarre({ segment, capacite }: { segment: Segment; capacite: number }): ReactElement {
  const largeur = `${((segment.octets / Math.max(capacite, 1)) * 100).toFixed(3)}%`;
  const infobulle = `${segment.libelle} — ${formaterOctets(segment.octets)}. ${segment.justification}`;
  return (
    <motion.div className="h-6" initial={false} animate={{ width: largeur }} transition={transitionLayout}>
      <Tooltip content={infobulle} className="h-full w-full">
        <span
          className={cn('block h-full w-full', segment.hachure && 'eh-hatched')}
          style={segment.hachure ? undefined : { backgroundColor: TONE_VAR[segment.tone] }}
        />
      </Tooltip>
    </motion.div>
  );
}

interface BarreProps {
  titre: string;
  capaciteOctets: number;
  echelle: number;
  segments: Segment[];
  mesure: string;
}

function BarreRessource({ titre, capaciteOctets, echelle, segments, mesure }: BarreProps): ReactElement {
  const part = `${((capaciteOctets / echelle) * 100).toFixed(3)}%`;
  return (
    <div className="min-w-0">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-2">
        <span className="text-xs text-text-2">{titre}</span>
        <span className="font-mono text-xs tabular-nums text-text">{mesure}</span>
      </div>
      {/* Largeur en pourcentage de l'échelle commune : la barre suit le conteneur, elle ne suppose
          aucune largeur de colonne. */}
      <div className="flex overflow-hidden rounded-xs bg-surface-2" style={{ width: part }}>
        {segments.map((segment) => (
          <SegmentBarre key={segment.cle} segment={segment} capacite={capaciteOctets} />
        ))}
      </div>
    </div>
  );
}

function LigneLegende({ segment }: { segment: Segment }): ReactElement {
  return (
    <li className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
      <span
        aria-hidden="true"
        className={cn('h-2 w-2 shrink-0 rounded-xs', segment.hachure && 'eh-hatched')}
        style={segment.hachure ? undefined : { backgroundColor: TONE_VAR[segment.tone] }}
      />
      <span className="min-w-0 flex-1 truncate text-2xs text-text-2">{segment.libelle}</span>
      <span className="shrink-0 font-mono text-2xs tabular-nums text-text">
        {formaterOctets(segment.octets)}
      </span>
      {/* Sans survol, l'infobulle n'est pas le seul porteur de la justification : elle est écrite
          sous la valeur. La densité de bureau la remet dans l'infobulle seule. */}
      <span className="w-full break-words pl-3.5 text-2xs leading-snug text-text-3 lg:hidden">
        {segment.justification}
      </span>
    </li>
  );
}

function Legende({ segments }: { segments: Segment[] }): ReactElement {
  return (
    // Une colonne au doigt : à deux colonnes dans un tiroir étroit, le libellé est tronqué au point
    // de ne plus nommer le poste, ce qui est justement le rôle de la légende.
    <ul className="grid grid-cols-1 gap-x-3 gap-y-1 lg:grid-cols-2">
      {segments.map((segment) => (
        <LigneLegende key={segment.cle} segment={segment} />
      ))}
    </ul>
  );
}

export interface BarresMemoireProps {
  plan: PlanDeChargement;
  /** VRAM totale du GPU, mesurée par le domaine `system` — l'échelle de la barre, pas un budget. */
  vramTotaleOctets: number;
}

export function BarresMemoire({ plan, vramTotaleOctets }: BarresMemoireProps): ReactElement {
  const budget = plan.budget;
  const { vram, ram } = useMemo(
    () => construireSegments(plan, vramTotaleOctets),
    [plan, vramTotaleOctets],
  );
  // Somme des postes affichés, pas un calcul de plan : le backend expose la décomposition et non
  // son total (la propriété `vram_requise_octets` n'est pas sérialisée). Additionner des lignes
  // déjà décidées ne rejoue aucun arbitrage.
  const vramRequise = budget.postes.reduce((total, poste) => total + poste.octets, 0);
  const echelle = Math.max(vramTotaleOctets, budget.ram_disponible_octets, 1);
  const mesureVram = `${formaterOctets(vramRequise)} sur ${formaterOctets(vramTotaleOctets)}`;
  const mesureRam = `${formaterOctets(budget.ram_requise_octets)} sur ${formaterOctets(budget.ram_disponible_octets)}`;
  return (
    <div className="space-y-3">
      <BarreRessource
        titre="VRAM"
        capaciteOctets={vramTotaleOctets}
        echelle={echelle}
        segments={vram}
        mesure={mesureVram}
      />
      <BarreRessource
        titre="RAM hôte disponible"
        capaciteOctets={budget.ram_disponible_octets}
        echelle={echelle}
        segments={ram}
        mesure={mesureRam}
      />
      <Legende segments={[...vram, ...ram]} />
    </div>
  );
}
