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
