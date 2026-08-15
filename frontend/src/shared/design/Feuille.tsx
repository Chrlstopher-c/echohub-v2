/*
 * Tiroir latéral — la forme que prennent les colonnes du chat sous 1024 px.
 *
 * Panneau LATÉRAL et non feuille par le bas : les deux contenus concernés (liste de conversations,
 * plan d'exécution) sont des listes verticales longues, qu'une feuille basse écraserait au tiers de
 * la hauteur. Le panneau recouvre le fil sans le remplacer, donc le contexte reste derrière le voile.
 *
 * Au-dessus du seuil, ce composant est un PASSE-PLAT : aucun portal, aucun voile, la colonne
 * reprend sa place en flux. C'est ce qui permet aux écrans de n'avoir qu'une seule mise en page.
 */

import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useEffect, useRef } from 'react';
import type { ReactElement, ReactNode, RefObject } from 'react';
import { createPortal } from 'react-dom';

import { cn } from './cn';
import { DUR, EASE_OUT } from './motion';
import { useEstGrandEcran } from './useEstGrandEcran';

export type CoteFeuille = 'gauche' | 'droite';

export interface FeuilleProps {
  readonly ouverte: boolean;
  readonly onFermer: () => void;
  readonly cote: CoteFeuille;
  /** Titre de l'entête du tiroir — obligatoire : un panneau sans nom n'est pas repérable. */
  readonly titre: string;
  readonly className?: string;
  readonly children: ReactNode;
}

const SELECTEUR_FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const ANCRAGE: Record<CoteFeuille, string> = {
  gauche: 'left-0 border-r w-[min(20rem,88vw)]',
  droite: 'right-0 border-l w-[min(24rem,92vw)]',
};

/** Renvoie la tabulation au début du panneau quand elle en sort — le focus n'atteint jamais le fond. */
function boucler(evenement: KeyboardEvent, panneau: HTMLElement): void {
  const cibles = Array.from(panneau.querySelectorAll<HTMLElement>(SELECTEUR_FOCUSABLE));
  const premier = cibles[0];
  const dernier = cibles[cibles.length - 1];
  // Un test sur `length` ne restreint pas le type sous `noUncheckedIndexedAccess` : c'est
  // l'accès indexé lui-même qui rend `HTMLElement | undefined`. On interroge donc les deux
  // valeurs, ce qui couvre aussi le panneau sans élément atteignable.
  if (premier === undefined || dernier === undefined) {
    return;
  }
  const courant = document.activeElement;
  if (evenement.shiftKey && (courant === premier || !panneau.contains(courant))) {
    evenement.preventDefault();
    dernier.focus();
  } else if (!evenement.shiftKey && courant === dernier) {
    evenement.preventDefault();
    premier.focus();
  }
}

/** Échap ferme, le fond ne défile plus, et le focus ne sort pas du panneau tant qu'il est ouvert. */
function usePiegeFocus(panneau: RefObject<HTMLElement>, actif: boolean, onFermer: () => void): void {
  useEffect(() => {
    if (!actif) {
      return undefined;
    }
    const precedemmentActif = document.activeElement;
    const surTouche = (evenement: KeyboardEvent): void => {
      if (evenement.key === 'Escape') {
        onFermer();
      } else if (evenement.key === 'Tab' && panneau.current !== null) {
        boucler(evenement, panneau.current);
      }
    };
    document.addEventListener('keydown', surTouche);
    const defilementPrecedent = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panneau.current?.querySelector<HTMLElement>(SELECTEUR_FOCUSABLE)?.focus();
    return (): void => {
      document.removeEventListener('keydown', surTouche);
      document.body.style.overflow = defilementPrecedent;
      if (precedemmentActif instanceof HTMLElement) {
        precedemmentActif.focus();
      }
    };
  }, [actif, onFermer, panneau]);
}

function BoutonFermer({ onFermer }: { readonly onFermer: () => void }): ReactElement {
  return (
    <button
      type="button"
      onClick={onFermer}
      aria-label="Fermer le panneau"
      className={cn(
        'inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-sm text-text-2',
        'transition-colors duration-fast hover:bg-surface-2 hover:text-text',
        'focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--ring)]',
      )}
    >
      <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden="true">
        <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </button>
  );
}

function Voile({ onFermer, reduit }: { readonly onFermer: () => void; readonly reduit: boolean }): ReactElement {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: reduit ? 0 : DUR.fast }}
      onClick={onFermer}
      aria-hidden="true"
      className="absolute inset-0 bg-scrim"
    />
  );
}

interface PanneauFeuilleProps extends Omit<FeuilleProps, 'ouverte'> {
  readonly reduit: boolean;
}

function PanneauFeuille({ onFermer, cote, titre, className, reduit, children }: PanneauFeuilleProps): ReactElement {
  const panneau = useRef<HTMLDivElement>(null);
  usePiegeFocus(panneau, true, onFermer);
  const depart = cote === 'gauche' ? '-100%' : '100%';
  return (
    <div className="fixed inset-0 z-40">
      <Voile onFermer={onFermer} reduit={reduit} />
      <motion.div
        ref={panneau}
        role="dialog"
        aria-modal="true"
        aria-label={titre}
        initial={{ x: reduit ? 0 : depart }}
        animate={{ x: 0 }}
        exit={{ x: reduit ? 0 : depart }}
        transition={{ duration: reduit ? 0 : DUR.slow, ease: EASE_OUT }}
        className={cn(
          'absolute inset-y-0 flex flex-col border-border bg-surface shadow-3',
          ANCRAGE[cote],
          className,
        )}
      >
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border pl-3 pr-1">
          <h2 className="min-w-0 truncate text-md font-semibold text-text">{titre}</h2>
          <BoutonFermer onFermer={onFermer} />
        </header>
        <div className="eh-marge-sure-bas min-h-0 flex-1 overflow-y-auto overflow-x-hidden">{children}</div>
      </motion.div>
    </div>
  );
}

export function Feuille({ ouverte, onFermer, cote, titre, className, children }: FeuilleProps): ReactElement {
  const estGrandEcran = useEstGrandEcran();
  const reduit = useReducedMotion() === true;
  if (estGrandEcran) {
    return <>{children}</>;
  }
  return createPortal(
    <AnimatePresence>
      {ouverte && (
        <PanneauFeuille onFermer={onFermer} cote={cote} titre={titre} className={className} reduit={reduit}>
          {children}
        </PanneauFeuille>
      )}
    </AnimatePresence>,
    document.body,
  );
}
