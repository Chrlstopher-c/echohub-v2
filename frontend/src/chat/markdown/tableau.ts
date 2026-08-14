/*
 * Lecture des tableaux à barres verticales (convention GFM), la forme qu'émettent les modèles quand
 * on leur demande de comparer quoi que ce soit.
 *
 * Un tableau n'est reconnu que sur la présence de sa ligne de délimiteurs, de même largeur que
 * l'en-tête. Cette exigence évite qu'une phrase contenant une barre verticale devienne un tableau,
 * et elle est ce qui rend le streaming tolérable : tant que la ligne `|---|---|` n'est pas arrivée,
 * l'en-tête s'affiche comme du texte, puis se réorganise en tableau au fragment suivant.
 */

import { ligneA } from './acces';
import { analyserInline } from './inline';
import type { Alignement, Avance, SegmentInline } from './types';

const MOTIF_DELIMITEUR = /^:?-+:?$/;
const SEPARATEUR_CELLULE = /(?<!\\)\|/;

/** Découpe une rangée en cellules. Les barres échappées (`\|`) restent du contenu. */
function cellules(ligne: string): string[] {
  const nu = ligne.trim().replace(/^\|/, '').replace(/\|$/, '');
  return nu.split(SEPARATEUR_CELLULE).map((cellule) => cellule.replace(/\\\|/g, '|').trim());
}

function alignementDe(delimiteur: string): Alignement {
  const gauche = delimiteur.startsWith(':');
  const droite = delimiteur.endsWith(':');
  if (gauche && droite) {
    return 'centre';
  }
  return droite ? 'droite' : 'gauche';
}

/** Vrai si les lignes `depart` et `depart + 1` forment un en-tête suivi de ses délimiteurs. */
export function estTableau(lignes: string[], depart: number): boolean {
  const entete = ligneA(lignes, depart);
  const delimiteurs = ligneA(lignes, depart + 1);
  if (!entete.includes('|') || !delimiteurs.includes('|')) {
    return false;
  }
  const colonnes = cellules(delimiteurs);
  return (
    colonnes.length > 0 &&
    colonnes.every((colonne) => MOTIF_DELIMITEUR.test(colonne)) &&
    cellules(entete).length === colonnes.length
  );
}

function estRangee(ligne: string): boolean {
  return ligne.trim() !== '' && ligne.includes('|');
}

/** Complète une rangée courte : une cellule manquante vaut vide, elle ne décale pas les colonnes. */
function normaliser(brutes: string[], colonnes: number): SegmentInline[][] {
  const rangee = brutes.map(analyserInline);
  while (rangee.length < colonnes) {
    rangee.push([]);
  }
  return rangee;
}

/**
 * Lit le tableau à partir de son en-tête. Le corps peut être vide — c'est l'état normal pendant le
 * streaming, juste après l'arrivée des délimiteurs : on montre l'en-tête plutôt que rien.
 */
export function lireTableau(lignes: string[], depart: number): Avance {
  const entetes = cellules(ligneA(lignes, depart)).map(analyserInline);
  const alignements = cellules(ligneA(lignes, depart + 1)).map(alignementDe);
  const corps: SegmentInline[][][] = [];
  let i = depart + 2;
  // Borne : chaque tour consomme une ligne, et la première ligne non conforme arrête la lecture.
  while (i < lignes.length && estRangee(ligneA(lignes, i))) {
    corps.push(normaliser(cellules(ligneA(lignes, i)), entetes.length));
    i += 1;
  }
  return { bloc: { type: 'tableau', entetes, alignements, lignes: corps }, suivant: i };
}
