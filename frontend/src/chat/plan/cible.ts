import type { DemandeDeChargement } from '../api/contrats';

/*
 * Ce que l'écran de chat doit recevoir pour pouvoir faire planifier un chargement.
 *
 * Le domaine `chat` n'assemble PAS cette structure : lire les métadonnées d'un GGUF appartient au
 * domaine `models`, mesurer la machine au domaine `system`. Les fabriquer ici obligerait le chat à
 * connaître deux domaines et à reproduire leurs conversions — exactement la duplication que la v2
 * refuse. Le chat les reçoit, les transmet au planificateur, et affiche ce qui revient.
 */
export interface CibleChargement {
  /** Chemin du fichier de poids, résolu par le domaine `models`. */
  cheminModele: string;
  /** Nom affichable du modèle sélectionné. */
  nomModele: string;
  /**
   * Entrées mesurées du planificateur. La référence doit être stable entre deux rendus : elle est
   * la dépendance de la replanification.
   */
  demande: DemandeDeChargement;
}
