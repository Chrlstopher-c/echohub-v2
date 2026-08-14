/*
 * Interface publique du panneau de contexte — seul point d'import autorisé depuis le reste de
 * l'écran de chat. Le découpage interne (barre, hook, vocabulaire des postes) doit pouvoir changer
 * sans toucher l'appelant.
 *
 * Usage :
 *   <PanneauContexte messages={messagesMoteur} promptSysteme={…} modeleCharge={…} />
 */

export { PanneauContexte, type PanneauContexteProps } from './PanneauContexte';
export { useOccupationContexte, type EntreeOccupation, type EtatOccupation } from './useOccupationContexte';
