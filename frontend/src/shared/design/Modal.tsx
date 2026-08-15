import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { cn } from './cn';
import { overlayFade, panelIn } from './motion';

/*
 * `xl` est le mode AGRANDI (plan d'exécution, lot L3) : jusque-là la primitive ne connaissait que
 * des tailles figées choisies par l'appelant. `xl` est différent des trois autres — ce n'est pas
 * un choix de l'appelant, c'est une taille que l'UTILISATEUR atteint en cliquant le bouton
 * d'agrandissement (`expansible`, ci-dessous), pour un contenu qui a besoin de place à la demande
 * (un artefact de code ou un aperçu HTML), sans forcer cette taille à chaque ouverture.
 */
export type ModalSize = 'sm' | 'md' | 'lg' | 'xl';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Zone d'actions en pied (boutons de confirmation) — la primitive n'en impose pas. */
  footer?: ReactNode;
  size?: ModalSize;
  /** Contenu additionnel dans l'en-tête, entre le titre et les boutons (ex. un interrupteur). */
  actionsEntete?: ReactNode;
  /** Affiche le bouton d'agrandissement/réduction dans l'en-tête — voir `ModalSize.xl`. */
  expansible?: boolean;
  children: ReactNode;
}

const SIZE: Record<ModalSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-5xl',
};

/* Seul le mode agrandi contraint une hauteur : les autres tailles restent la hauteur de leur
 * contenu, comme avant ce lot — rien ne doit bouger pour un appelant qui ignore `expansible`. */
const HAUTEUR_CORPS: Record<ModalSize, string> = {
  sm: '',
  md: '',
  lg: '',
  xl: 'max-h-[70vh] overflow-y-auto',
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

function BoutonAgrandir({ agrandi, onBasculer }: { agrandi: boolean; onBasculer: () => void }): ReactElement {
  return (
    <button
      type="button"
      onClick={onBasculer}
      aria-label={agrandi ? 'Réduire' : 'Agrandir'}
      title={agrandi ? 'Réduire' : 'Agrandir'}
      className="rounded-xs p-1 text-text-2 transition-colors duration-fast hover:bg-surface-2 hover:text-text"
    >
      {agrandi ? (
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" aria-hidden="true">
          <path
            d="M6.5 9.5 3 13m0 0h3m-3 0v-3M9.5 6.5 13 3m0 0h-3m3 0v3"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" aria-hidden="true">
          <path
            d="M10 3h3v3M13 3 9.5 6.5M6 13H3v-3M3 13l3.5-3.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}

interface PanelHeaderProps {
  title: string;
  actionsEntete?: ReactNode;
  expansible: boolean;
  agrandi: boolean;
  onBasculerAgrandi: () => void;
  onClose: () => void;
}

function PanelHeader({
  title,
  actionsEntete,
  expansible,
  agrandi,
  onBasculerAgrandi,
  onClose,
}: PanelHeaderProps): ReactElement {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
      <h2 className="min-w-0 truncate text-md font-semibold text-text">{title}</h2>
      <div className="flex shrink-0 items-center gap-1">
        {actionsEntete}
        {expansible && <BoutonAgrandir agrandi={agrandi} onBasculer={onBasculerAgrandi} />}
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
      </div>
    </header>
  );
}

type ModalPanelProps = Omit<ModalProps, 'open' | 'size'> & {
  size: ModalSize;
  agrandi: boolean;
  onBasculerAgrandi: () => void;
};

function ModalPanel({
  title,
  footer,
  actionsEntete,
  expansible = false,
  size,
  agrandi,
  onBasculerAgrandi,
  children,
  onClose,
}: ModalPanelProps): ReactElement {
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
        'relative flex w-full flex-col rounded-lg border border-border-strong bg-overlay shadow-3',
        SIZE[size],
      )}
    >
      <PanelHeader
        title={title}
        actionsEntete={actionsEntete}
        expansible={expansible}
        agrandi={agrandi}
        onBasculerAgrandi={onBasculerAgrandi}
        onClose={onClose}
      />
      <div className={cn('px-4 py-4', HAUTEUR_CORPS[size])}>{children}</div>
      {footer !== undefined && (
        <footer className="flex justify-end gap-2 border-t border-border px-4 py-3">{footer}</footer>
      )}
    </motion.div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  footer,
  actionsEntete,
  expansible = false,
  size = 'md',
  children,
}: ModalProps): ReactElement {
  useModalEffects(open, onClose);
  // Réinitialisé à chaque fermeture : rouvrir un artefact repart toujours en taille normale, pas
  // dans l'état laissé par la consultation précédente — un choix d'affichage, pas une préférence.
  const [agrandi, setAgrandi] = useState<boolean>(false);
  useEffect((): void => {
    if (!open) {
      setAgrandi(false);
    }
  }, [open]);
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
          <ModalPanel
            title={title}
            footer={footer}
            actionsEntete={actionsEntete}
            expansible={expansible}
            size={agrandi ? 'xl' : size}
            agrandi={agrandi}
            onBasculerAgrandi={() => setAgrandi((courant) => !courant)}
            onClose={onClose}
          >
            {children}
          </ModalPanel>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
