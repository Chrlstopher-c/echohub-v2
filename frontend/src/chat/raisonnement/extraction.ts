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

/**
 * Fermeture qui apparaît AVANT toute ouvrante — le cas réellement observé, et non un cas limite.
 *
 * Les gabarits de conversation Qwen3 et DeepSeek-R1 placent eux-mêmes `<think>` à la fin du prompt
 * pour amorcer le raisonnement. Le modèle n'a donc plus à l'émettre : le flux commence directement
 * par la réflexion et ne porte que `</think>`. Chercher l'ouvrante en premier ne trouve alors rien,
 * et l'intégralité du raisonnement s'affiche comme s'il s'agissait de la réponse.
 *
 * Mesuré sur cette machine : c'est le comportement de tous les modèles de raisonnement chargés.
 */
function fermetureOrpheline(source: string, depuis: number): Ouverture | null {
  let meilleure: Ouverture | null = null;
  for (const convention of CONVENTIONS_RAISONNEMENT) {
    const fin = source.indexOf(convention.fermante, depuis);
    if (fin < 0) {
      continue;
    }
    const ouvrante = source.indexOf(convention.ouvrante, depuis);
    // Une ouvrante située avant cette fermeture signifie un bloc normal : ce n'est pas notre cas.
    if (ouvrante >= 0 && ouvrante < fin) {
      continue;
    }
    if (meilleure === null || fin < meilleure.index) {
      meilleure = { convention, index: fin };
    }
  }
  return meilleure;
}

/*
 * Marqueur posé par le backend à la fin d'un tour ayant demandé un outil. Ce qui le précède est le
 * commentaire de travail du modèle — « je vais chercher », « j'ai 6 résultats, je synthétise » —
 * et non sa réponse. Le laisser dans le texte visible le faisait passer pour la réponse, et la
 * vraie réponse arrivait ensuite comme si elle en était la suite.
 *
 * Il est retiré du texte rendu : c'est du balisage, pas du contenu.
 */
const MARQUEUR_FIN_ETAPE = '<etape-fin/>';

/**
 * Découpe la source sur les marqueurs d'étape, et rend les commentaires de travail comme des
 * segments repliables — au même titre qu'un raisonnement, puisque c'est la même nature : du
 * cheminement, pas la réponse.
 *
 * Seul le DERNIER fragment est la réponse. Tout ce qui précède un marqueur appartient à un tour
 * qui s'est conclu par un appel d'outil.
 */
export function segmenterReponse(source: string): ReponseSegmentee {
  if (!source.includes(MARQUEUR_FIN_ETAPE)) {
    return _segmenter(source);
  }
  const parts = source.split(MARQUEUR_FIN_ETAPE);
  // `pop` ne peut pas rendre `undefined` : `split` rend toujours au moins un élément.
  const finale = parts.pop() ?? '';
  const etapes: SegmentRaisonnement[] = [];
  for (const part of parts) {
    const morceau = _segmenter(part);
    const commentaire = morceau.visible.trim();
    // Le commentaire précède presque toujours les balises du tour : le modèle annonce ce qu'il
    // va faire, PUIS appelle. On le place donc en tête quand la part commence par du texte libre,
    // ce qui restitue l'ordre réel — commentaire, appel, résultat — au lieu de le rejeter après.
    const commenceParDuTexte = _premiereBalise(part) !== 0;
    if (commentaire !== '' && commenceParDuTexte) {
      etapes.push({ convention: 'etape', texte: commentaire, complet: true });
    }
    etapes.push(...morceau.raisonnements);
    if (commentaire !== '' && !commenceParDuTexte) {
      etapes.push({ convention: 'etape', texte: commentaire, complet: true });
    }
  }
  const derniere = _segmenter(finale);
  return {
    visible: derniere.visible,
    raisonnements: [...etapes, ...derniere.raisonnements],
    enCours: derniere.enCours,
  };
}

/** Position de la première balise ouvrante, ou la longueur du texte s'il n'y en a aucune. */
function _premiereBalise(source: string): number {
  const debut = source.trimStart();
  const decalage = source.length - debut.length;
  const ouverture = prochaineOuverture(debut, 0);
  return ouverture === null ? source.length : ouverture.index + decalage;
}

interface EtatDecoupe {
  visible: string[];
  raisonnements: SegmentRaisonnement[];
  curseur: number;
}

/** Consomme un bloc ouvert par une balise. Rend `null` si le bloc n'est jamais refermé. */
function _consommerBloc(source: string, etat: EtatDecoupe, ouverture: Ouverture): EtatDecoupe | null {
  const { convention, index } = ouverture;
  etat.visible.push(source.slice(etat.curseur, index));
  const debut = index + convention.ouvrante.length;
  const fin = source.indexOf(convention.fermante, debut);
  if (fin < 0) {
    // Bloc jamais refermé : tout le reste du texte reçu lui appartient. Rien n'est mis en attente,
    // sinon un raisonnement en cours resterait invisible jusqu'à la fin de la génération.
    etat.raisonnements.push({ convention: convention.nom, texte: source.slice(debut), complet: false });
    return null;
  }
  etat.raisonnements.push({ convention: convention.nom, texte: source.slice(debut, fin), complet: true });
  return { ...etat, curseur: fin + convention.fermante.length };
}

/** Referme un bloc dont seule la balise fermante existe (amorcé par le gabarit, voir plus haut). */
function _consommerOrpheline(source: string, etat: EtatDecoupe, orpheline: Ouverture): EtatDecoupe {
  const texte = source.slice(etat.curseur, orpheline.index);
  etat.raisonnements.push({ convention: orpheline.convention.nom, texte, complet: true });
  return { ...etat, curseur: orpheline.index + orpheline.convention.fermante.length };
}

function _segmenter(source: string): ReponseSegmentee {
  let etat: EtatDecoupe = { visible: [], raisonnements: [], curseur: 0 };
  for (let tour = 0; tour < toursMax(source); tour += 1) {
    /*
     * Deux cas concourent, et c'est LE PLUS PROCHE du curseur qui l'emporte — pas l'un des deux
     * systématiquement.
     *
     * Traiter la fermeture orpheline d'abord, sans comparer, faisait avaler tout ce qui la
     * précédait : un bloc d'outil complet se retrouvait absorbé dans un segment de raisonnement,
     * étiqueté « Raisonnement » alors qu'il contenait l'entrée et la sortie d'une recherche.
     * Observé le 2026-08-15 sur une réponse où le modèle refermait son `</think>` APRÈS le
     * résultat de l'outil.
     *
     * En comparant les positions, les blocs ressortent dans leur ordre d'apparition réel :
     * raisonnement, appel, résultat, réponse.
     */
    const orpheline = fermetureOrpheline(source, etat.curseur);
    const ouverture = prochaineOuverture(source, etat.curseur);
    if (orpheline !== null && (ouverture === null || orpheline.index < ouverture.index)) {
      etat = _consommerOrpheline(source, etat, orpheline);
      continue;
    }
    if (ouverture === null) {
      break;
    }
    const suite = _consommerBloc(source, etat, ouverture);
    if (suite === null) {
      return { visible: etat.visible.join(''), raisonnements: etat.raisonnements, enCours: true };
    }
    etat = suite;
  }
  etat.visible.push(source.slice(etat.curseur));
  return { visible: etat.visible.join(''), raisonnements: etat.raisonnements, enCours: false };
}
