/*
 * Interface publique du domaine design — seul point d'import autorisé pour les
 * autres domaines. Les CSS (tokens, fonts, primitives) s'importent une fois au
 * point d'entrée de l'app ; le préset s'importe dans tailwind.config.
 */

export { Button, type ButtonProps, type ButtonSize, type ButtonVariant } from './Button';
export { Card, type CardLevel, type CardProps } from './Card';
export { Badge, type BadgeProps } from './Badge';
export { Slider, type SliderProps, type SliderZone } from './Slider';
export { Progress, type ProgressProps } from './Progress';
export { Tooltip, type TooltipProps } from './Tooltip';
export { Modal, type ModalProps, type ModalSize } from './Modal';

export {
  MenuContextuel,
  type ApiMenuContextuel,
  type EntreeMenu,
  type MenuContextuelProps,
} from './MenuContextuel';
/* ---- Briques tactiles : ce que les écrans utilisent sous le seuil de 1024 px ---- */
export { Feuille, type CoteFeuille, type FeuilleProps } from './Feuille';
export { BoutonActions, type BoutonActionsProps } from './BoutonActions';
export { useEstGrandEcran } from './useEstGrandEcran';
export { useHauteurVisuelle } from './useHauteurVisuelle';

export { TONE_SOFT_VAR, TONE_VAR, type Tone } from './tones';
export {
  DUR,
  EASE_IN_OUT,
  EASE_OUT,
  fadeUp,
  overlayFade,
  panelIn,
  tooltipIn,
  transitionBase,
  transitionLayout,
  transitionSlow,
} from './motion';
export { cn } from './cn';
export { designPreset } from './tailwind-preset';
