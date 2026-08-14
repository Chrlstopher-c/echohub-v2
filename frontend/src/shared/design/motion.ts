import type { Transition, Variants } from 'framer-motion';

/*
 * Vocabulaire de mouvement partagé — mêmes valeurs que tokens.css (Framer Motion
 * ne lit pas les variables CSS dans ses transitions, d'où la duplication assumée ici,
 * et nulle part ailleurs).
 */

export const DUR = {
  fast: 0.12,
  base: 0.18,
  slow: 0.28,
} as const;

export const EASE_OUT = [0.16, 1, 0.3, 1] as const;
export const EASE_IN_OUT = [0.65, 0, 0.35, 1] as const;

export const transitionBase: Transition = { duration: DUR.base, ease: EASE_OUT };
export const transitionSlow: Transition = { duration: DUR.slow, ease: EASE_OUT };

/* Réagencements de layout (cellules de couches qui migrent VRAM → RAM). */
export const transitionLayout: Transition = { duration: DUR.slow, ease: EASE_IN_OUT };

/* Apparition d'un contenu : léger décalage vertical, jamais de rebond. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0, transition: transitionBase },
  exit: { opacity: 0, y: 6, transition: { duration: DUR.fast, ease: EASE_OUT } },
};

/* Voile des modales. */
export const overlayFade: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: DUR.base } },
  exit: { opacity: 0, transition: { duration: DUR.fast } },
};

/* Panneau de modale : décélération franche, amplitude contenue. */
export const panelIn: Variants = {
  hidden: { opacity: 0, y: 12, scale: 0.98 },
  visible: { opacity: 1, y: 0, scale: 1, transition: transitionSlow },
  exit: { opacity: 0, y: 8, scale: 0.98, transition: { duration: DUR.fast, ease: EASE_OUT } },
};

/* Tooltip : présence discrète, quasi instantanée. */
export const tooltipIn: Variants = {
  hidden: { opacity: 0, y: 3 },
  visible: { opacity: 1, y: 0, transition: { duration: DUR.fast, ease: EASE_OUT } },
  exit: { opacity: 0, transition: { duration: 0.08 } },
};
