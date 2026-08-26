/*
 * Détection d'un artefact dans un segment de raisonnement.
 *
 * `presenter_fichier` (`backend/outils/presenter_fichier.py`) est un outil comme un autre : son
 * résultat traverse les mêmes balises `<entree>`/`<sortie>` que tout appel (`appel-outil.ts`). Ce
 * qui le distingue est son CONTENU — un JSON compact plutôt qu'un texte libre — reconnu ici pour
 * remplacer le rendu générique entrée/sortie par une carte cliquable dans le fil.
 */

import type { AppelOutil } from '../raisonnement/appel-outil';
import { decouperAppel } from '../raisonnement/appel-outil';
import type { SegmentRaisonnement } from '../raisonnement/extraction';

export type OrigineArtefact = 'utilisateur' | 'modele';

export interface ArtefactPresente {
  readonly fichier_id: string;
  readonly nom_affiche: string;
  readonly type_mime: string;
  readonly taille_octets: number;
  readonly origine: OrigineArtefact;
}

const NOM_OUTIL = 'presenter_fichier';

function estForme(valeur: unknown): valeur is ArtefactPresente {
  if (typeof valeur !== 'object' || valeur === null) {
    return false;
  }
  const objet = valeur as Record<string, unknown>;
  return (
    typeof objet['fichier_id'] === 'string' &&
    typeof objet['nom_affiche'] === 'string' &&
    typeof objet['type_mime'] === 'string' &&
    typeof objet['taille_octets'] === 'number' &&
    (objet['origine'] === 'utilisateur' || objet['origine'] === 'modele')
  );
}

/**
 * Rend l'artefact désigné si `appel` est un appel COMPLET et réussi de `presenter_fichier`.
 * `null` sinon : un autre outil, un échec (texte libre, pas du JSON), ou une sortie encore
 * incomplète pendant le streaming — le JSON n'est alors pas encore clos, et l'appelant doit
 * retomber sur le rendu générique le temps que le tour se termine.
 */
export function artefactDepuisAppel(appel: AppelOutil): ArtefactPresente | null {
  if (!appel.entree.startsWith(`${NOM_OUTIL}(`) || !appel.termine) {
    return null;
  }
  try {
    const donnees: unknown = JSON.parse(appel.sortie);
    return estForme(donnees) ? donnees : null;
  } catch {
    return null;
  }
}

/** Même détection, à partir du segment de raisonnement complet — ce que `ReponseModele` manipule. */
export function artefactDepuisSegment(segment: SegmentRaisonnement): ArtefactPresente | null {
  if (segment.convention !== 'outil') {
    return null;
  }
  const appel = decouperAppel(segment.texte);
  return appel === null ? null : artefactDepuisAppel(appel);
}

/* ------------------------------------------------------------------ artefacts versionnés */

/*
 * `creer_artefact` (contrat proposé au backend, voir le rapport de refonte) CRÉE un contenu et le
 * présente — là où `presenter_fichier` DÉSIGNE un fichier qui existe déjà. Les deux gestes
 * partagent l'enveloppe `<entree>`/`<sortie>` et le principe du JSON compact ; la forme créée
 * porte en plus l'identité de l'artefact, son type de rendu et son numéro de version, parce que
 * le modèle corrigera son artefact et que chaque correction doit rester consultable.
 */

/** Types dont l'atelier sait faire quelque chose. Tout autre mot est ramené à `inconnu`. */
export const TYPES_ARTEFACT = ['html', 'markdown', 'code', 'svg', 'mermaid'] as const;
export type TypeArtefact = (typeof TYPES_ARTEFACT)[number];

export interface VersionArtefact {
  /** Identité STABLE à travers les versions — c'est elle qui relie v1, v2, v3. */
  readonly artefact_id: string;
  /** Numéro croissant, attribué par le backend. Jamais recalculé ici. */
  readonly version: number;
  readonly titre: string;
  /** `inconnu` = mot hors liste : le contenu s'affiche alors en texte brut, jamais en page vide. */
  readonly type: TypeArtefact | 'inconnu';
  /** Langage de coloration pour `type === 'code'` ; `null` ailleurs. */
  readonly langage: string | null;
  /** Fichier qui porte le contenu de CETTE version — servi par `/api/fichiers/{id}`. */
  readonly fichier_id: string;
  readonly taille_octets: number;
}

const NOM_OUTIL_CREATION = 'creer_artefact';

function typeConnu(valeur: unknown): TypeArtefact | 'inconnu' {
  return (TYPES_ARTEFACT as readonly string[]).includes(valeur as string) ? (valeur as TypeArtefact) : 'inconnu';
}

/*
 * Validation champ par champ : la sortie vient d'un outil, mais ses valeurs ont traversé un
 * modèle — même traitement qu'une entrée utilisateur. Un type hors liste ne rejette PAS
 * l'artefact (le contenu reste lisible en texte brut) ; un champ d'identité manquant, si.
 */
function versionDepuisJson(valeur: unknown): VersionArtefact | null {
  if (typeof valeur !== 'object' || valeur === null) {
    return null;
  }
  const objet = valeur as Record<string, unknown>;
  const identite =
    typeof objet['artefact_id'] === 'string' &&
    typeof objet['fichier_id'] === 'string' &&
    typeof objet['titre'] === 'string' &&
    typeof objet['version'] === 'number' &&
    Number.isInteger(objet['version']) &&
    (objet['version'] as number) >= 1 &&
    typeof objet['taille_octets'] === 'number';
  if (!identite) {
    return null;
  }
  return {
    artefact_id: objet['artefact_id'] as string,
    version: objet['version'] as number,
    titre: objet['titre'] as string,
    type: typeConnu(objet['type']),
    langage: typeof objet['langage'] === 'string' ? objet['langage'] : null,
    fichier_id: objet['fichier_id'] as string,
    taille_octets: objet['taille_octets'] as number,
  };
}

/**
 * Rend la version présentée si `appel` est un appel COMPLET de `creer_artefact` dont la sortie est
 * le JSON attendu. `null` sinon — l'appelant retombe sur la carte d'outil générique, exactement
 * comme pour `presenter_fichier`.
 */
export function versionDepuisAppel(appel: AppelOutil): VersionArtefact | null {
  if (!appel.entree.startsWith(`${NOM_OUTIL_CREATION}(`) || !appel.termine) {
    return null;
  }
  try {
    return versionDepuisJson(JSON.parse(appel.sortie));
  } catch {
    return null;
  }
}

/** Même détection, à partir du segment complet — le pendant de `artefactDepuisSegment`. */
export function versionDepuisSegment(segment: SegmentRaisonnement): VersionArtefact | null {
  if (segment.convention !== 'outil') {
    return null;
  }
  const appel = decouperAppel(segment.texte);
  return appel === null ? null : versionDepuisAppel(appel);
}
