import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { cn } from './cn';
import { tooltipIn } from './motion';

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

export function Tooltip({
  content,
  side = 'top',
  delay = 250,
  className,
  children,
}: TooltipProps): ReactElement {
  const [open, setOpen] = useState<boolean>(false);
  const timer = useRef<number | undefined>(undefined);

  // Un seul timer, toujours nettoyé : pas de tooltip orphelin après démontage.
  useEffect(() => (): void => window.clearTimeout(timer.current), []);

  const show = (): void => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), delay);
  };
  const hide = (): void => {
    window.clearTimeout(timer.current);
    setOpen(false);
  };

  return (
    <span
      className={cn('relative inline-flex', className)}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      <AnimatePresence>{open && <Bubble side={side}>{content}</Bubble>}</AnimatePresence>
    </span>
  );
}

function Bubble({ side, children }: { side: 'top' | 'bottom'; children: ReactNode }): ReactElement {
  return (
    <motion.span
      role="tooltip"
      variants={tooltipIn}
      initial="hidden"
      animate="visible"
      exit="exit"
      className={cn(
        'pointer-events-none absolute left-1/2 z-50 w-max max-w-[16rem] -translate-x-1/2',
        'rounded-sm border border-border-strong bg-overlay px-2 py-1 text-2xs text-text shadow-2',
        SIDE[side],
      )}
    >
      {children}
    </motion.span>
  );
}
