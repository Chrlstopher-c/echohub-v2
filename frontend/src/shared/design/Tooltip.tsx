import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  HTMLAttributes,
  KeyboardEvent as KeyboardEventReact,
  ReactElement,
  ReactNode,
  RefObject,
} from 'react';
import { cn } from './cn';
import { tooltipIn } from './motion';

/*
 * Infobulle — et son chemin tactile.
 *
 * Sur un appareil sans survol, une infobulle au survol n'apparaît JAMAIS : son contenu est
 * purement absent. Quand le pointeur ne sait pas survoler (`hover: none`), l'enveloppe devient donc
 * déclenchable à l'appui, annoncée à l'assistance vocale, et la bulle reste ouverte jusqu'au
 * prochain appui ailleurs ou à Échap.
 *
 * Cela ne dispense PAS l'appelant : une information qui n'existe QUE dans une infobulle reste une
 * information cachée. Le contrat impose de rendre les justifications du plan en texte sous la
 * valeur — l'infobulle est un complément, jamais l'unique porteur.
 */

export interface TooltipProps {
  /** Contenu explicatif — typiquement la justification d'une valeur du plan. */
  content: ReactNode;
  side?: 'top' | 'bottom';
  /** Délai avant apparition (ms) — évite le clignotement en survol de listes. */
  delay?: number;
  className?: string;
  children: ReactNode;
}

const SIDE: Record<NonNullable<TooltipProps['side']>, string> = {
  top: 'bottom-full mb-1.5',
  bottom: 'top-full mt-1.5',
};

/** Le pointeur sait-il survoler ? Une souris oui, un doigt non — un hybride bascule à chaud. */
function useSurvolDisponible(): boolean {
  const [disponible, setDisponible] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return true;
    }
    return window.matchMedia('(hover: hover)').matches;
  });
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const liste = window.matchMedia('(hover: hover)');
    const surChangement = (evenement: MediaQueryListEvent): void => setDisponible(evenement.matches);
    setDisponible(liste.matches);
    liste.addEventListener('change', surChangement);
    return (): void => liste.removeEventListener('change', surChangement);
  }, []);
  return disponible;
}

/** Ferme au prochain appui hors de l'enveloppe et à Échap — sinon la bulle resterait collée. */
function useFermetureExterieure(actif: boolean, hote: RefObject<HTMLElement>, fermer: () => void): void {
  useEffect(() => {
    if (!actif) {
      return undefined;
    }
    const surPointeur = (evenement: PointerEvent): void => {
      const cible = evenement.target;
      if (cible instanceof Node && hote.current?.contains(cible) === true) {
        return;
      }
      fermer();
    };
    const surTouche = (evenement: KeyboardEvent): void => {
      if (evenement.key === 'Escape') fermer();
    };
    window.addEventListener('pointerdown', surPointeur, true);
    window.addEventListener('keydown', surTouche);
    return (): void => {
      window.removeEventListener('pointerdown', surPointeur, true);
      window.removeEventListener('keydown', surTouche);
    };
  }, [actif, hote, fermer]);
}

/** Sans survol, l'enveloppe devient elle-même un déclencheur annoncé — sinon la bulle est inatteignable. */
function gestesTactiles(open: boolean, basculer: () => void): HTMLAttributes<HTMLSpanElement> {
  return {
    role: 'button',
    tabIndex: 0,
    'aria-expanded': open,
    onClick: basculer,
    onKeyDown: (evenement: KeyboardEventReact<HTMLSpanElement>): void => {
      if (evenement.key === 'Enter' || evenement.key === ' ') {
        evenement.preventDefault();
        basculer();
      }
    },
  };
}

export function Tooltip({ content, side = 'top', delay = 250, className, children }: TooltipProps): ReactElement {
  const [open, setOpen] = useState<boolean>(false);
  const timer = useRef<number | undefined>(undefined);
  const hote = useRef<HTMLSpanElement>(null);
  const survolDisponible = useSurvolDisponible();

  // Un seul timer, toujours nettoyé : pas de tooltip orphelin après démontage.
  useEffect(() => (): void => window.clearTimeout(timer.current), []);

  const hide = useCallback((): void => {
    window.clearTimeout(timer.current);
    setOpen(false);
  }, []);
  const show = (): void => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), delay);
  };
  const basculer = (): void => setOpen((courant) => !courant);

  useFermetureExterieure(open && !survolDisponible, hote, hide);

  const gestes: HTMLAttributes<HTMLSpanElement> = survolDisponible
    ? { onMouseEnter: show, onMouseLeave: hide, onFocus: show, onBlur: hide }
    : gestesTactiles(open, basculer);

  return (
    <span ref={hote} className={cn('relative inline-flex', className)} {...gestes}>
      {children}
      <AnimatePresence>
        {open && (
          <Bubble side={side} interactive={!survolDisponible}>
            {content}
          </Bubble>
        )}
      </AnimatePresence>
    </span>
  );
}

interface BubbleProps {
  readonly side: 'top' | 'bottom';
  /** Au doigt la bulle doit rester pointable : c'est elle qui porte le contenu à lire. */
  readonly interactive: boolean;
  readonly children: ReactNode;
}

function Bubble({ side, interactive, children }: BubbleProps): ReactElement {
  return (
    <motion.span
      role="tooltip"
      variants={tooltipIn}
      initial="hidden"
      animate="visible"
      exit="exit"
      className={cn(
        'absolute left-1/2 z-50 w-max max-w-[min(16rem,80vw)] -translate-x-1/2',
        'rounded-sm border border-border-strong bg-overlay px-2 py-1 text-2xs text-text shadow-2',
        interactive ? 'pointer-events-auto' : 'pointer-events-none',
        SIDE[side],
      )}
    >
      {children}
    </motion.span>
  );
}
