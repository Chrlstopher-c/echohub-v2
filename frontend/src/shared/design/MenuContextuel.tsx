/*
 * Menu contextuel — clic droit, et clavier.
 *
 * Générique et sans dépendance à un domaine : il reçoit des entrées et les rend. C'est ce qui
 * permet de l'utiliser sur une conversation, un message ou un modèle sans le réécrire.
 *
 * Trois exigences non négociables, et chacune corrige un défaut courant de ce type de composant :
 *
 * - **Le clavier ouvre aussi le menu.** La touche Menu et Shift+F10 sont les équivalents clavier du
 *   clic droit ; s'en remettre à la souris seule rendrait ces actions inatteignables.
 * - **Le menu ne sort jamais de l'écran.** Sa position est corrigée après mesure, pas devinée : un
 *   clic droit en bas de la liste ouvrirait sinon un menu à moitié invisible.
 * - **Une action destructrice est signalée**, et ne referme le menu qu'après avoir été déclenchée.
 *
 * Le menu natif du navigateur reste accessible partout où aucun menu n'est défini : on ne supprime
 * pas le clic droit du système, on l'enrichit là où l'application a quelque chose à proposer.
 */

import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactElement, ReactNode } from 'react';

import { cn } from './cn';
import { TONE_VAR } from './tones';

/** Marge conservée avec le bord de la fenêtre lors du recadrage. */
const MARGE_ECRAN = 8;

export interface EntreeMenu {
  readonly libelle: string;
  readonly onChoisir: () => void;
  /** Rend l'entrée inerte, sans la cacher : une action absente est plus déroutante qu'une action grisée. */
  readonly desactivee?: boolean;
  /** Colore l'entrée en critique et l'isole des autres. */
  readonly destructive?: boolean;
  readonly raccourci?: string;
}

interface Position {
  readonly x: number;
  readonly y: number;
}

interface PanneauProps {
  readonly position: Position;
  readonly entrees: readonly EntreeMenu[];
  readonly onFermer: () => void;
}

function Panneau({ position, entrees, onFermer }: PanneauProps): ReactElement {
  const panneau = useRef<HTMLDivElement>(null);
  const [corrigee, setCorrigee] = useState<Position>(position);

  // Recadrage APRÈS mesure : la taille du menu dépend de ses entrées, donc elle n'est connue
  // qu'une fois rendu. `useLayoutEffect` évite l'image intermédiaire hors écran.
  useLayoutEffect(() => {
    const boite = panneau.current?.getBoundingClientRect();
    if (boite === undefined) {
      return;
    }
    const debordeX = position.x + boite.width - window.innerWidth + MARGE_ECRAN;
    const debordeY = position.y + boite.height - window.innerHeight + MARGE_ECRAN;
    setCorrigee({
      x: debordeX > 0 ? Math.max(MARGE_ECRAN, position.x - boite.width) : position.x,
      y: debordeY > 0 ? Math.max(MARGE_ECRAN, position.y - debordeY) : position.y,
    });
  }, [position]);

  useEffect(() => {
    const surTouche = (evenement: KeyboardEvent): void => {
      if (evenement.key === 'Escape') onFermer();
    };
    // `capture` : le menu se ferme avant que le clic n'atteigne l'élément visé, sinon un clic
    // ailleurs déclencherait l'action de cet autre élément en plus de fermer le menu.
    window.addEventListener('keydown', surTouche);
    window.addEventListener('pointerdown', onFermer, true);
    window.addEventListener('scroll', onFermer, true);
    return () => {
      window.removeEventListener('keydown', surTouche);
      window.removeEventListener('pointerdown', onFermer, true);
      window.removeEventListener('scroll', onFermer, true);
    };
  }, [onFermer]);

  return (
    <motion.div
      ref={panneau}
      role="menu"
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.09, ease: 'easeOut' }}
      style={{ left: corrigee.x, top: corrigee.y }}
      className="fixed z-50 min-w-[11rem] origin-top-left rounded-md border border-border bg-surface-2 p-1 shadow-lg"
      onContextMenu={(evenement) => evenement.preventDefault()}
    >
      {entrees.map((entree, index) => (
        <button
          key={entree.libelle}
          type="button"
          role="menuitem"
          disabled={entree.desactivee}
          onClick={() => {
            entree.onChoisir();
            onFermer();
          }}
          className={cn(
            'flex w-full items-center justify-between gap-6 rounded-sm px-2 py-1.5 text-left text-xs',
            'transition-colors duration-fast ease-out',
            'focus-visible:outline-none focus-visible:shadow-[inset_0_0_0_2px_var(--ring)]',
            entree.desactivee ? 'cursor-not-allowed text-text-3' : 'text-text-2 hover:bg-surface-3 hover:text-text',
            entree.destructive && !entree.desactivee && 'hover:bg-critical-soft',
            // Les actions destructrices sont séparées du reste : un clic mal placé ne doit pas
            // tomber sur « supprimer » parce qu'il est collé à « renommer ».
            entree.destructive && index > 0 && 'mt-1 border-t border-border pt-2',
          )}
          style={entree.destructive && !entree.desactivee ? { color: TONE_VAR.critical } : undefined}
        >
          <span>{entree.libelle}</span>
          {entree.raccourci !== undefined && (
            <span className="font-mono text-2xs text-text-3">{entree.raccourci}</span>
          )}
        </button>
      ))}
    </motion.div>
  );
}

export interface MenuContextuelProps {
  readonly entrees: readonly EntreeMenu[];
  readonly children: ReactNode;
  readonly className?: string;
}

/** Enveloppe un élément et lui attache un menu au clic droit, à la touche Menu et à Shift+F10. */
export function MenuContextuel({ entrees, children, className }: MenuContextuelProps): ReactElement {
  const [position, setPosition] = useState<Position | null>(null);
  const fermer = useCallback((): void => setPosition(null), []);

  const surClavier = useCallback((evenement: React.KeyboardEvent<HTMLDivElement>): void => {
    if (evenement.key !== 'ContextMenu' && !(evenement.shiftKey && evenement.key === 'F10')) {
      return;
    }
    evenement.preventDefault();
    // Sans souris, le menu s'ancre sur l'élément lui-même plutôt que sur un curseur inexistant.
    const boite = evenement.currentTarget.getBoundingClientRect();
    setPosition({ x: boite.left + 8, y: boite.bottom - 4 });
  }, []);

  return (
    <div
      className={className}
      onContextMenu={(evenement) => {
        evenement.preventDefault();
        setPosition({ x: evenement.clientX, y: evenement.clientY });
      }}
      onKeyDown={surClavier}
    >
      {children}
      <AnimatePresence>
        {position !== null && <Panneau position={position} entrees={entrees} onFermer={fermer} />}
      </AnimatePresence>
    </div>
  );
}
