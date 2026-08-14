/*
 * Interface publique du domaine `models`.
 *
 * L'écran, plus le vocabulaire de faisabilité — c'est le seul concept du domaine dont un autre
 * écran peut avoir besoin (afficher « tient en VRAM » à côté d'un modèle, ailleurs).
 *
 * Ce qui n'est PAS exposé : le client HTTP, les routes, les hooks d'écran, les composants internes.
 */

export { EcranModeles, type EcranModelesProps } from './EcranModeles';
export { PastilleFaisabilite, BandeauReserve } from './faisabilite/Faisabilite';
export {
  budgetDepuis,
  evaluer,
  LIBELLE_VERDICT,
  RESERVE,
  type BudgetMemoire,
  type Faisabilite,
  type Verdict,
} from './faisabilite/evaluation';
export type { ModeleEnregistre, Telechargement, ResultatRecherche } from './api/types';
