/*
 * Interface publique du domaine `system`.
 *
 * Seul point d'import autorisé depuis un autre domaine. Le domaine `models` s'en sert pour situer
 * une taille de modèle par rapport à la mémoire réellement libre : sans mesure, aucun verdict de
 * faisabilité n'est défendable.
 *
 * Surface volontairement étroite. Ce qui n'est PAS exposé : le client HTTP, les routes, le hook de
 * sondage, les composants d'écran. Ce sont des internes ; les exposer figerait leur découpe.
 */

export { EcranSysteme } from './EcranSysteme';
export { useProfilMachine, type EtatProfil } from './materiel/useProfilMachine';
export type { ContraintesPlateforme, Gpu, Memoire, Plateforme, ProfilMachine } from './api/types';
