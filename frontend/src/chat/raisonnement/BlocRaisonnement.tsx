import { AnimatePresence, motion } from 'framer-motion';
import { useId, useState } from 'react';
import type { ReactElement } from 'react';
import { Badge, cn, DUR, fadeUp } from '../../shared/design';
import { LIBELLE_CONVENTION } from './conventions';
import type { SegmentRaisonnement } from './extraction';

/*
 * Le raisonnement d'un modèle, replié par défaut.
 *
 * Parti pris de lecture (DESIGN.md) : ce bloc doit se lire comme SECONDAIRE. D'où trois choix —
 *   - il n'est pas rendu en Markdown, contrairement à la réponse : un flux de pensée n'est pas un
 *     document, et lui donner la même typographie qu'à la réponse le mettrait au même rang visuel ;
 *   - l'ambre (`--caution`) n'apparaît que sur le badge, jamais en aplat : c'est déjà la famille du
 *     poste « raisonnement » dans le panneau de contexte (voir `contexte/postes.ts`) — du budget
 *     dépensé pour un texte que l'utilisateur ne relit pas, donc un compromis, pas une erreur ;
 *   - la mesure affichée est un NOMBRE DE CARACTÈRES, pas une estimation de tokens. Le décompte en
 *     tokens existe, mesuré par le backend dans le panneau de contexte ; le convertir ici à la
 *     louche (« 4 caractères = 1 token ») donnerait deux chiffres contradictoires à l'écran.
 *
 * Un bloc non refermé le dit, mais ne pulse QUE si la génération est réellement en cours : le pouls
 * annonce une activité, et un raisonnement coupé par `max_tokens` est un texte figé, pas un travail.
 */

const CARACTERES = new Intl.NumberFormat('fr-FR');
/* Un raisonnement peut faire plusieurs milliers de caractères : déplié, il défile chez lui plutôt
 * que de pousser la réponse hors de l'écran. */
const CLASSE_DEFILEMENT = 'max-h-72 overflow-y-auto';

function Chevron({ ouvert }: { ouvert: boolean }): ReactElement {
  return (
    <motion.svg
      viewBox="0 0 12 12"
      className="h-3 w-3 shrink-0"
      fill="none"
      aria-hidden="true"
      animate={{ rotate: ouvert ? 90 : 0 }}
      transition={{ duration: DUR.fast }}
    >
      <path d="M4.5 2.5 8 6l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </motion.svg>
  );
}

function EtatBloc({ segment, actif }: { segment: SegmentRaisonnement; actif: boolean }): ReactElement | null {
  if (segment.complet) {
    return null;
  }
  return (
    <Badge tone="caution" pulse={actif} dot={!actif} className="ml-auto">
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
        'flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-left text-xs text-text-3',
        'transition-colors duration-fast ease-out hover:text-text-2',
        'focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--ring)]',
      )}
    >
      <Chevron ouvert={ouvert} />
      {/* Le libellé suit la convention du segment : un appel d'outil et une réflexion se replient
          de la même façon, mais doivent se distinguer d'un coup d'œil. */}
      <span className="font-medium">
        {LIBELLE_CONVENTION[segment.convention] ?? 'Raisonnement'}
        {rang !== null ? ` ${rang}` : ''}
      </span>
      <span className="font-mono text-2xs tabular-nums">
        {CARACTERES.format(segment.texte.length)} caractères
      </span>
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
    <section className="rounded-sm border border-border bg-surface">
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
            <div className={cn('border-t border-border px-2.5 py-2', CLASSE_DEFILEMENT)}>
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
