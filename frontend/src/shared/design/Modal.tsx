import { AnimatePresence, motion } from 'framer-motion';
import { useEffect } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { cn } from './cn';
import { overlayFade, panelIn } from './motion';

export type ModalSize = 'sm' | 'md' | 'lg';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Zone d'actions en pied (boutons de confirmation) — la primitive n'en impose pas. */
  footer?: ReactNode;
  size?: ModalSize;
  children: ReactNode;
}

const SIZE: Record<ModalSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
};

/* Échap ferme, et le fond ne défile plus tant que la modale est ouverte. */
function useModalEffects(open: boolean, onClose: () => void): void {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return (): void => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);
}

function PanelHeader({ title, onClose }: { title: string; onClose: () => void }): ReactElement {
  return (
    <header className="flex items-center justify-between border-b border-border px-4 py-3">
      <h2 className="text-md font-semibold text-text">{title}</h2>
      <button
        type="button"
        onClick={onClose}
        aria-label="Fermer"
        className="rounded-xs p-1 text-text-2 transition-colors duration-fast hover:bg-surface-2 hover:text-text"
      >
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" aria-hidden="true">
          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
    </header>
  );
}

function ModalPanel({ title, footer, size, children, onClose }: Omit<ModalProps, 'open'> & {
  size: ModalSize;
}): ReactElement {
  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      variants={panelIn}
      initial="hidden"
      animate="visible"
      exit="exit"
      className={cn(
        'relative w-full rounded-lg border border-border-strong bg-overlay shadow-3',
        SIZE[size],
      )}
    >
      <PanelHeader title={title} onClose={onClose} />
      <div className="px-4 py-4">{children}</div>
      {footer !== undefined && (
        <footer className="flex justify-end gap-2 border-t border-border px-4 py-3">{footer}</footer>
      )}
    </motion.div>
  );
}

export function Modal({ open, onClose, title, footer, size = 'md', children }: ModalProps): ReactElement {
  useModalEffects(open, onClose);
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            variants={overlayFade}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={onClose}
            className="absolute inset-0 bg-scrim"
            aria-hidden="true"
          />
          <ModalPanel title={title} footer={footer} size={size} onClose={onClose}>
            {children}
          </ModalPanel>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
