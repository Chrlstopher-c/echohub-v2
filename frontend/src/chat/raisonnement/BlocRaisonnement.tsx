/*
 * Le raisonnement d'un modèle, replié par défaut — la version SECONDAIRE de la grammaire des
 * cartes : même chevron, même mécanique de dépliage que `CarteOutil`, mais sans surface propre.
 * Un outil a agi sur le monde, il mérite une carte ; une réflexion n'est qu'un cheminement, elle
 * ne réclame qu'une ligne discrète.
 *
 * Trois choix conservés de la version précédente, pour les mêmes raisons mesurées :
 *   - pas de Markdown : un flux de pensée n'est pas un document, même typographie = même rang ;
 *   - la mesure est un NOMBRE DE CARACTÈRES, pas une estimation de tokens — le vrai décompte vit
 *     dans le panneau de contexte, et deux chiffres contradictoires à l'écran seraient pires ;
 *   - le pouls n'apparaît que si la génération est réellement en cours : un raisonnement coupé
 *     par `max_tokens` est un texte figé, pas un travail.
 */

import { AnimatePresence, motion } from 'framer-motion';
import { useId, useState } from 'react';
import type { ReactElement } from 'react';
import { Badge, cn, fadeUp } from '../../shared/design';
import { Chevron } from './Chevron';
import { LIBELLE_CONVENTION } from './conventions';
import type { SegmentRaisonnement } from './extraction';

const CARACTERES = new Intl.NumberFormat('fr-FR');

/* Un raisonnement peut faire plusieurs milliers de caractères : déplié, il défile chez lui plutôt
 * que de pousser la réponse hors de l'écran. */
const CLASSE_DEFILEMENT = 'max-h-72 overflow-y-auto overflow-x-auto overscroll-contain';

function EtatBloc({ segment, actif }: { segment: SegmentRaisonnement; actif: boolean }): ReactElement | null {
  if (segment.complet) {
    return null;
  }
  return (
    <Badge tone="caution" pulse={actif} dot={!actif}>
      {actif ? 'en cours' : 'non refermé'}
    </Badge>
  );
}

interface EnteteProps {
  segment: SegmentRaisonnement;
  rang: number | null;
  actif: boolean;
  ouvert: boolean;
  cible: string;
  onBasculer: () => void;
}

function Entete({ segment, rang, actif, ouvert, cible, onBasculer }: EnteteProps): ReactElement {
  return (
    <button
      type="button"
      onClick={onBasculer}
      aria-expanded={ouvert}
      aria-controls={cible}
      className={cn(
        // `flex-wrap` sans point de rupture : à 390 px le libellé, le décompte et le badge ne
        // tiennent pas sur une ligne ; ils passent dessous plutôt que d'être rognés.
        'flex w-full min-h-[44px] flex-wrap items-center gap-x-2 gap-y-1 rounded-sm px-2.5 py-2',
        'text-left text-2xs text-text-3 lg:min-h-0 lg:flex-nowrap lg:py-1',
        'transition-colors duration-fast ease-out hover:bg-surface hover:text-text-2',
        'focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--ring)]',
      )}
    >
      <Chevron ouvert={ouvert} />
      {/* Le libellé suit la convention du segment : une réflexion et une note de travail se
          replient de la même façon mais doivent se distinguer d'un coup d'œil. */}
      <span className="font-medium">
        {LIBELLE_CONVENTION[segment.convention] ?? 'Raisonnement'}
        {rang !== null ? ` ${rang}` : ''}
      </span>
      <span className="font-mono tabular-nums">{CARACTERES.format(segment.texte.length)} car.</span>
      <EtatBloc segment={segment} actif={actif} />
    </button>
  );
}

export interface BlocRaisonnementProps {
  segment: SegmentRaisonnement;
  /** Rang affiché quand la réponse contient plusieurs blocs ; `null` s'il est seul. */
  rang: number | null;
  /** La génération est réellement en cours — seul cas où l'activité s'anime. */
  actif: boolean;
}

export function BlocRaisonnement({ segment, rang, actif }: BlocRaisonnementProps): ReactElement {
  const [ouvert, setOuvert] = useState<boolean>(false);
  const cible = useId();
  const vide = segment.texte.trim() === '';
  return (
    <section className="max-w-full">
      <Entete
        segment={segment}
        rang={rang}
        actif={actif}
        ouvert={ouvert}
        cible={cible}
        onBasculer={() => setOuvert(!ouvert)}
      />
      <AnimatePresence initial={false}>
        {ouvert && (
          <motion.div id={cible} variants={fadeUp} initial="hidden" animate="visible" exit="exit">
            {/* Retrait aligné sous le libellé, pas de trait : l'espace suffit à rattacher le
                contenu à sa ligne, un cadre en ferait un bloc au même rang que les cartes. */}
            <div className={cn('pb-1 pl-7 pr-2.5', CLASSE_DEFILEMENT)}>
              <p className={cn('whitespace-pre-wrap text-xs leading-relaxed', vide ? 'text-text-3' : 'text-text-2')}>
                {vide ? 'Bloc vide : le modèle a ouvert puis refermé son raisonnement.' : segment.texte}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
