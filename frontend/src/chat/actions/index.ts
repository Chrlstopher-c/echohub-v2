/*
 * Interface publique du module `actions` du domaine chat.
 *
 * Il n'expose que trois choses : l'état à monter dans l'écran (`useActionsFil`), le fournisseur qui
 * porte les capacités jusqu'aux messages, et l'enveloppe à poser autour d'un message. Tout le
 * reste — flux, gestes, aperçu, presse-papiers — est interne et remplaçable sans prévenir.
 */

export { useActionsFil, type EtatActionsFil } from './useActionsFil';
export {
  FournisseurActions,
  type ActionsMessages,
  type FournisseurActionsProps,
} from './fournisseur';
export { EnveloppeMessage, type EnveloppeMessageProps } from './EnveloppeMessage';
