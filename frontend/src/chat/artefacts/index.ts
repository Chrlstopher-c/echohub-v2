/*
 * Interface publique du domaine `artefacts` (plan d'exécution, lot L3) — seul point d'import
 * autorisé pour les autres domaines.
 */

export { CarteArtefact, type CarteArtefactProps } from './CarteArtefact';
export { ModaleArtefact, type ModaleArtefactProps } from './ModaleArtefact';
export { artefactDepuisAppel, artefactDepuisSegment, type ArtefactPresente, type OrigineArtefact } from './detection';
export { decrireLangage, type DescriptionLangage } from './langage';
