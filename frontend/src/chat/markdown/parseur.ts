/*
 * Analyse Markdown maison, calibrée sur ce qu'écrit réellement un modèle : titres, listes (avec
 * imbrication), tableaux, citations, blocs de code, séparateurs, et l'inline courant.
 *
 * Écrit ici plutôt qu'ajouté en dépendance pour une raison de sûreté : le résultat est un arbre de
 * données que React rend en éléments, donc aucun HTML n'est jamais injecté. Un rendu passant par
 * `dangerouslySetInnerHTML` exigerait un assainisseur, soit une seconde dépendance à auditer.
 *
 * L'analyse tolère l'inachevé, parce que le texte arrive fragment par fragment : une clôture de
 * bloc de code manquante donne un bloc `complet: false`, un tableau sans rangée s'affiche réduit à
 * son en-tête, un marqueur inline ouvert ressort en texte. À aucun moment un texte déjà reçu ne
 * disparaît de l'écran parce que sa construction n'est pas terminée.
 *
 * Les lecteurs vivent dans des fichiers séparés (`liste.ts`, `tableau.ts`, `inline.ts`) ; ce fichier
 * ne fait qu'aiguiller ligne à ligne.
 */

import { CLOTURE_CODE, groupe, ligneA } from './acces';
import { analyserInline } from './inline';
import { analyserMarque, lireListe } from './liste';
import { estTableau, lireTableau } from './tableau';
import type { Avance, BlocMarkdown, NiveauTitre } from './types';

const MOTIF_TITRE = /^(#{1,6})\s+(.*)$/;
const MOTIF_CITATION = /^>\s?(.*)$/;
const MOTIF_SEPARATEUR = /^(-{3,}|\*{3,}|_{3,})$/;
const NIVEAU_MAX = 6;

function niveauTitre(dieses: string): NiveauTitre {
  // Le motif borne déjà la longueur à 6 : le cast nomme cette garantie au lieu d'ajouter un test
  // qui ne pourrait jamais échouer, et `Math.min` la rend vraie même si le motif changeait.
  return Math.min(dieses.length, NIVEAU_MAX) as NiveauTitre;
}

function lireCode(lignes: string[], depart: number): Avance {
  const langage = ligneA(lignes, depart).slice(CLOTURE_CODE.length).trim();
  const corps: string[] = [];
  let i = depart + 1;
  while (i < lignes.length && !ligneA(lignes, i).startsWith(CLOTURE_CODE)) {
    corps.push(ligneA(lignes, i));
    i += 1;
  }
  const complet = i < lignes.length;
  return {
    bloc: { type: 'code', langage, texte: corps.join('\n'), complet },
    suivant: complet ? i + 1 : i,
  };
}

function lireCitation(lignes: string[], depart: number): Avance {
  const parties: string[] = [];
  let i = depart;
  let trouve = MOTIF_CITATION.exec(ligneA(lignes, i));
  while (trouve !== null) {
    parties.push(groupe(trouve, 1));
    i += 1;
    trouve = i < lignes.length ? MOTIF_CITATION.exec(ligneA(lignes, i)) : null;
  }
  return { bloc: { type: 'citation', contenu: analyserInline(parties.join(' ')) }, suivant: i };
}

function lireParagraphe(lignes: string[], depart: number): Avance {
  const parties: string[] = [];
  let i = depart;
  while (i < lignes.length && ligneA(lignes, i).trim() !== '' && !estDebutDeBloc(lignes, i)) {
    parties.push(ligneA(lignes, i).trim());
    i += 1;
  }
  return { bloc: { type: 'paragraphe', contenu: analyserInline(parties.join(' ')) }, suivant: i };
}

/* Un paragraphe s'arrête là où un autre bloc commence. Le tableau se teste sur deux lignes : sa
 * détection dépend de la ligne de délimiteurs, pas de la ligne courante seule. */
function estDebutDeBloc(lignes: string[], index: number): boolean {
  const ligne = ligneA(lignes, index);
  return (
    ligne.startsWith(CLOTURE_CODE) ||
    MOTIF_TITRE.test(ligne) ||
    MOTIF_CITATION.test(ligne) ||
    MOTIF_SEPARATEUR.test(ligne.trim()) ||
    analyserMarque(ligne) !== null ||
    estTableau(lignes, index)
  );
}

/* Ordre significatif : le séparateur passe avant la liste (`---` n'est pas un item vide), et le
 * tableau avant la citation et le paragraphe (une rangée n'est ni l'un ni l'autre). */
function lireBloc(lignes: string[], depart: number): Avance {
  const ligne = ligneA(lignes, depart);
  if (ligne.startsWith(CLOTURE_CODE)) {
    return lireCode(lignes, depart);
  }
  const titre = MOTIF_TITRE.exec(ligne);
  if (titre !== null) {
    const bloc: BlocMarkdown = {
      type: 'titre',
      niveau: niveauTitre(groupe(titre, 1)),
      contenu: analyserInline(groupe(titre, 2)),
    };
    return { bloc, suivant: depart + 1 };
  }
  if (MOTIF_SEPARATEUR.test(ligne.trim())) {
    return { bloc: { type: 'separateur' }, suivant: depart + 1 };
  }
  if (estTableau(lignes, depart)) {
    return lireTableau(lignes, depart);
  }
  const marque = analyserMarque(ligne);
  if (marque !== null) {
    return lireListe(lignes, depart, marque.indentation, 0);
  }
  if (MOTIF_CITATION.test(ligne)) {
    return lireCitation(lignes, depart);
  }
  return lireParagraphe(lignes, depart);
}

export function analyserMarkdown(source: string): BlocMarkdown[] {
  const lignes = source.split('\n');
  const blocs: BlocMarkdown[] = [];
  let i = 0;
  // Chaque itération consomme au moins une ligne : la boucle est bornée par le nombre de lignes.
  while (i < lignes.length) {
    if (ligneA(lignes, i).trim() === '') {
      i += 1;
      continue;
    }
    const avance = lireBloc(lignes, i);
    blocs.push(avance.bloc);
    i = Math.max(avance.suivant, i + 1);
  }
  return blocs;
}
