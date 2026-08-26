/*
 * Interface publique du domaine `artefacts` (plan d'exécution, lot L3) — seul point d'import
 * autorisé pour les autres domaines.
 *
 * Deux gestes distincts y cohabitent : `presenter_fichier` DÉSIGNE un fichier existant (carte +
 * modale), `creer_artefact` CRÉE un contenu versionné qui s'ouvre dans l'atelier (carte + panneau).
 */

export { CarteArtefact, type CarteArtefactProps } from './CarteArtefact';
export { ModaleArtefact, type ModaleArtefactProps } from './ModaleArtefact';
export {
  artefactDepuisAppel,
  artefactDepuisSegment,
  versionDepuisAppel,
  versionDepuisSegment,
  TYPES_ARTEFACT,
  type ArtefactPresente,
  type OrigineArtefact,
  type TypeArtefact,
  type VersionArtefact,
} from './detection';
export { decrireLangage, type DescriptionLangage } from './langage';

/* ---- Atelier : artefacts créés et versionnés ---- */
export { CarteVersionArtefact, type CarteVersionArtefactProps } from './CarteVersionArtefact';
export { PanneauArtefact, type ChargeurContenu, type PanneauArtefactProps } from './PanneauArtefact';
export { VueArtefact, apercuPossible, type VueArtefactProps, type VueAtelier } from './VueArtefact';
export { useAtelier, type AtelierOuvert, type EtatAtelier } from './useAtelier';
export {
  FournisseurAtelier,
  useCapacitesAtelier,
  type CapacitesAtelier,
  type FournisseurAtelierProps,
} from './fournisseur-atelier';
export { collecterArtefacts, type ArtefactCatalogue, type MessageCollectable } from './versions';
