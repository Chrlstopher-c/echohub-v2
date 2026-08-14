/*
 * Lecture des listes, imbrication comprise.
 *
 * Le niveau d'une liste est son indentation MESURÉE sur la première ligne d'item, jamais un palier
 * supposé (« 2 espaces = un niveau ») : les modèles indentent à 2, 3 ou 4 espaces selon l'humeur du
 * gabarit, et un palier codé en dur ferait disparaître un niveau sur deux.
 *
 * Toute situation qu'on ne sait pas rattacher (sous-liste sans item parent, imbrication trop
 * profonde, second niveau au même endroit) clôt la liste au lieu d'écraser quoi que ce soit :
 * l'appelant relit la ligne comme une nouvelle liste, et aucun texte reçu n'est perdu.
 */

import { CLOTURE_CODE, groupe, ligneA } from './acces';
import { analyserInline } from './inline';
import type { AvanceListe, ItemListe } from './types';

const MOTIF_ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
/* Profondeur bornée : au-delà, l'affichage n'est de toute façon plus lisible, et la récursion
 * cesse d'être garantie finie sur une entrée pathologique (indentation croissante à chaque ligne). */
const PROFONDEUR_MAX = 6;
/* Une continuation appartient à l'item si elle dépasse son indentation d'au moins deux espaces. */
const RETRAIT_CONTINUATION = 2;

export interface Marque {
  indentation: number;
  ordonnee: boolean;
  texte: string;
}

/** Reconnaît une ligne d'item et mesure son indentation (une tabulation compte pour deux espaces). */
export function analyserMarque(ligne: string): Marque | null {
  const trouve = MOTIF_ITEM.exec(ligne);
  if (trouve === null) {
    return null;
  }
  const marqueur = groupe(trouve, 2);
  return {
    indentation: groupe(trouve, 1).replace(/\t/g, '  ').length,
    ordonnee: /\d/.test(marqueur),
    texte: groupe(trouve, 3),
  };
}

interface Cadre {
  indentation: number;
  ordonnee: boolean;
  profondeur: number;
}

/** Ligne indentée sous un item, sans marqueur : suite de son texte, ou fin de la liste. */
function continuation(lignes: string[], index: number, cadre: Cadre, items: ItemListe[]): number | null {
  const ligne = ligneA(lignes, index);
  if (ligne.trim() === '') {
    // Ligne vide : la liste ne se poursuit que si un item suit (liste « aérée »), sinon elle se clôt.
    const suivante = analyserMarque(ligneA(lignes, index + 1));
    return suivante !== null && suivante.indentation >= cadre.indentation ? index + 1 : null;
  }
  const dernier = items[items.length - 1];
  const retrait = ligne.length - ligne.trimStart().length;
  const rattachable = retrait >= cadre.indentation + RETRAIT_CONTINUATION;
  // Un bloc de code indenté sous un item est rendu au niveau supérieur plutôt qu'avalé en texte :
  // il resterait lisible, mais perdrait sa coloration et son bouton de copie.
  if (dernier === undefined || !rattachable || ligne.trimStart().startsWith(CLOTURE_CODE)) {
    return null;
  }
  dernier.contenu = [
    ...dernier.contenu,
    { type: 'texte', texte: ' ' },
    ...analyserInline(ligne.trim()),
  ];
  return index + 1;
}

/** Rattache une sous-liste au dernier item, ou clôt la liste si le rattachement est impossible. */
function imbriquer(lignes: string[], index: number, cadre: Cadre, items: ItemListe[], retrait: number): number | null {
  const dernier = items[items.length - 1];
  if (dernier === undefined || dernier.sousListe !== null || cadre.profondeur >= PROFONDEUR_MAX) {
    return null;
  }
  const sous = lireListe(lignes, index, retrait, cadre.profondeur + 1);
  dernier.sousListe = sous.bloc;
  return sous.suivant;
}

/** Traite la ligne `index` dans le cadre de la liste courante. Rend l'index suivant, ou `null` pour clore. */
function consommer(lignes: string[], index: number, cadre: Cadre, items: ItemListe[]): number | null {
  const marque = analyserMarque(ligneA(lignes, index));
  if (marque === null) {
    return continuation(lignes, index, cadre, items);
  }
  if (marque.indentation < cadre.indentation) {
    return null;
  }
  if (marque.indentation > cadre.indentation) {
    return imbriquer(lignes, index, cadre, items, marque.indentation);
  }
  if (marque.ordonnee !== cadre.ordonnee) {
    // Changement de nature au même niveau : c'est une autre liste, pas la suite de celle-ci.
    return null;
  }
  items.push({ contenu: analyserInline(marque.texte), sousListe: null });
  return index + 1;
}

/**
 * Lit une liste depuis `depart`, à l'indentation donnée. La nature (à puces ou numérotée) est celle
 * de la première ligne : c'est elle qui définit la liste, les suivantes s'y conforment ou la closent.
 */
export function lireListe(lignes: string[], depart: number, indentation: number, profondeur: number): AvanceListe {
  const premiere = analyserMarque(ligneA(lignes, depart));
  const cadre: Cadre = { indentation, ordonnee: premiere !== null && premiere.ordonnee, profondeur };
  const items: ItemListe[] = [];
  let i = depart;
  while (i < lignes.length) {
    const suivant = consommer(lignes, i, cadre, items);
    // Borne : un tour qui n'avance pas clôt la liste. Sans cette garde, une sous-liste qui refuse
    // de consommer sa première ligne ferait tourner la boucle indéfiniment.
    if (suivant === null || suivant <= i) {
      break;
    }
    i = suivant;
  }
  return { bloc: { type: 'liste', ordonnee: cadre.ordonnee, items }, suivant: i };
}
