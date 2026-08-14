/*
 * Interface publique du domaine `chat` — seul point d'import autorisé pour les autres domaines.
 *
 * Le domaine expose un écran et le contrat de ce qu'il faut lui fournir : le modèle sélectionné et
 * les entrées mesurées du planificateur. Il n'expose ni ses hooks, ni son client HTTP, ni ses
 * composants internes : ce sont des détails d'implémentation, remplaçables sans prévenir.
 */

export { ChatEcran, type ChatEcranProps } from './ChatEcran';
export type { CibleChargement } from './plan/cible';

/*
 * Types de contrat nécessaires pour construire une `CibleChargement`. Ils décrivent ce que le
 * backend attend ; les domaines `models` et `system` les remplissent à partir de leurs mesures.
 */
export type {
  DemandeDeChargement,
  FormatModele,
  MetadonneesModele,
  ModeleCharge,
  Moteur,
  PlateformePlan,
  PreferencesUtilisateur,
  ProfilMachinePlan,
  TypeCacheKV,
} from './api/contrats';
