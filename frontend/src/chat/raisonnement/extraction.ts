/*
 * Séparation d'une réponse de modèle en (texte visible, blocs de raisonnement).
 *
 * Miroir côté interface de `separer_raisonnement` (backend, `engines_adapters/contrat.py`), avec une
 * différence assumée : le backend GARDE les balises dans la part raisonnement, parce que ce sont des
 * tokens réellement renvoyés au modèle au tour suivant ; ici on les RETIRE, parce que « <think> »
 * affiché à l'écran n'est pas du raisonnement, c'est du balisage. Les deux découpent au même endroit.
 *
 * Trois situations arrivent en pratique et sont traitées explicitement :
 *   - balise ouverte jamais refermée (streaming en cours, ou génération coupée par `max_tokens`) :
 *     le bloc court jusqu'à la fin du texte reçu et se déclare incomplet ;
 *   - plusieurs blocs dans une même réponse : ils sont rendus dans l'ordre d'émission ;
 *   - texte visible vide parce que tout le budget est parti en raisonnement : `visible` vaut la
 *     chaîne vide, et c'est à l'appelant de le dire — la fonction ne comble rien.
 */

import { CONVENTIONS_RAISONNEMENT, type ConventionRaisonnement } from './conventions';

export interface SegmentRaisonnement {
  /** Nom de la convention qui a produit ce bloc — utile dès qu'il y en aura plusieurs. */
  readonly convention: string;
  /** Contenu du bloc, balises retirées. */
  readonly texte: string;
  /** `false` tant que la balise fermante n'est pas arrivée. */
  readonly complet: boolean;
}

export interface ReponseSegmentee {
  /** Tout ce qui n'est pas du raisonnement, dans l'ordre, recollé. */
  readonly visible: string;
  readonly raisonnements: readonly SegmentRaisonnement[];
  /** Un bloc est ouvert et non refermé : le modèle est (ou s'est arrêté) en plein raisonnement. */
  readonly enCours: boolean;
}

interface Ouverture {
  readonly convention: ConventionRaisonnement;
  readonly index: number;
}

/* Borne de la boucle principale : chaque tour consomme au moins une balise ouvrante entière. */
const LONGUEUR_OUVRANTE_MIN = Math.min(...CONVENTIONS_RAISONNEMENT.map((c) => c.ouvrante.length));

function toursMax(source: string): number {
  return Math.floor(source.length / LONGUEUR_OUVRANTE_MIN) + 1;
}

/** Première balise ouvrante à partir de `depuis`, toutes conventions confondues. */
function prochaineOuverture(source: string, depuis: number): Ouverture | null {
  let meilleure: Ouverture | null = null;
  for (const convention of CONVENTIONS_RAISONNEMENT) {
    const index = source.indexOf(convention.ouvrante, depuis);
    if (index >= 0 && (meilleure === null || index < meilleure.index)) {
      meilleure = { convention, index };
    }
  }
  return meilleure;
}

export function segmenterReponse(source: string): ReponseSegmentee {
  const visible: string[] = [];
  const raisonnements: SegmentRaisonnement[] = [];
  let curseur = 0;
  for (let tour = 0; tour < toursMax(source); tour += 1) {
    const ouverture = prochaineOuverture(source, curseur);
    if (ouverture === null) {
      break;
    }
    const { convention, index } = ouverture;
    visible.push(source.slice(curseur, index));
    const debut = index + convention.ouvrante.length;
    const fin = source.indexOf(convention.fermante, debut);
    if (fin < 0) {
      // Bloc jamais refermé : tout le reste du texte reçu lui appartient. Rien n'est mis en attente,
      // sinon un raisonnement en cours resterait invisible jusqu'à la fin de la génération.
      raisonnements.push({ convention: convention.nom, texte: source.slice(debut), complet: false });
      return { visible: visible.join(''), raisonnements, enCours: true };
    }
    raisonnements.push({ convention: convention.nom, texte: source.slice(debut, fin), complet: true });
    curseur = fin + convention.fermante.length;
  }
  visible.push(source.slice(curseur));
  return { visible: visible.join(''), raisonnements, enCours: false };
}
