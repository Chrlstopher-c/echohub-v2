/*
 * Analyse Markdown minimale, suffisante pour une réponse de modèle : titres, listes, citations,
 * blocs de code, séparateurs, et l'inline courant.
 *
 * Écrit ici plutôt qu'ajouté en dépendance pour une raison de sûreté : le résultat est un arbre de
 * données que React rend en éléments, donc aucun HTML n'est jamais injecté. Un rendu passant par
 * `dangerouslySetInnerHTML` exigerait un assainisseur, soit une seconde dépendance à auditer.
 *
 * L'analyse tolère l'inachevé : pendant le streaming, une clôture de bloc de code manquante donne
 * un bloc `complet: false` au lieu de faire disparaître le texte déjà reçu.
 */

export type SegmentInline =
  | { type: 'texte'; texte: string }
  | { type: 'fort'; texte: string }
  | { type: 'emphase'; texte: string }
  | { type: 'code'; texte: string }
  | { type: 'lien'; texte: string; href: string };

export type BlocMarkdown =
  | { type: 'titre'; niveau: 1 | 2 | 3; contenu: SegmentInline[] }
  | { type: 'paragraphe'; contenu: SegmentInline[] }
  | { type: 'code'; langage: string; texte: string; complet: boolean }
  | { type: 'liste'; ordonnee: boolean; items: SegmentInline[][] }
  | { type: 'citation'; contenu: SegmentInline[] }
  | { type: 'separateur' };

const MOTIF_INLINE = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*\n]+)\*|\[([^\]]+)\]\(([^)\s]+)\)/g;
const MOTIF_TITRE = /^(#{1,3})\s+(.*)$/;
const MOTIF_PUCE = /^[-*+]\s+(.*)$/;
const MOTIF_NUMERO = /^\d+[.)]\s+(.*)$/;
const MOTIF_CITATION = /^>\s?(.*)$/;
const MOTIF_SEPARATEUR = /^(-{3,}|\*{3,}|_{3,})$/;
const CLOTURE_CODE = '```';

/* Deux accès sont indexés hors garantie du typage, et `noUncheckedIndexedAccess` a raison de le
 * signaler : une ligne au-delà du tableau et un groupe de capture non apparié valent tous deux
 * `undefined` au runtime. Plutôt que de les taire par un cast, on les ramène à la chaîne vide —
 * neutre pour toutes les opérations qui suivent (`trim`, `startsWith`, `exec`). */
function ligneA(lignes: string[], index: number): string {
  return lignes[index] ?? '';
}

function groupe(trouve: RegExpExecArray, rang: number): string {
  return trouve[rang] ?? '';
}

function segmentDepuisCapture(trouve: RegExpExecArray): SegmentInline {
  // `RegExpExecArray` type ses éléments `string`, alors qu'un groupe non apparié vaut `undefined`
  // au runtime. Le réélargir ici évite de comparer à `undefined` un type qui prétend ne pas l'être.
  const groupes: Array<string | undefined> = trouve;
  if (groupes[1] !== undefined) {
    return { type: 'code', texte: groupes[1] };
  }
  if (groupes[2] !== undefined) {
    return { type: 'fort', texte: groupes[2] };
  }
  if (groupes[3] !== undefined) {
    return { type: 'emphase', texte: groupes[3] };
  }
  return { type: 'lien', texte: groupes[4] ?? '', href: groupes[5] ?? '' };
}

/** Découpe une ligne en segments typés. Le texte hors motif reste du texte brut. */
export function analyserInline(source: string): SegmentInline[] {
  const segments: SegmentInline[] = [];
  let curseur = 0;
  MOTIF_INLINE.lastIndex = 0;
  let trouve = MOTIF_INLINE.exec(source);
  while (trouve !== null) {
    if (trouve.index > curseur) {
      segments.push({ type: 'texte', texte: source.slice(curseur, trouve.index) });
    }
    segments.push(segmentDepuisCapture(trouve));
    curseur = trouve.index + trouve[0].length;
    trouve = MOTIF_INLINE.exec(source);
  }
  if (curseur < source.length) {
    segments.push({ type: 'texte', texte: source.slice(curseur) });
  }
  return segments;
}

interface Avance {
  bloc: BlocMarkdown;
  suivant: number;
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

function lireListe(lignes: string[], depart: number, ordonnee: boolean): Avance {
  const motif = ordonnee ? MOTIF_NUMERO : MOTIF_PUCE;
  const items: SegmentInline[][] = [];
  let i = depart;
  let trouve = motif.exec(ligneA(lignes, i));
  while (trouve !== null) {
    items.push(analyserInline(groupe(trouve, 1)));
    i += 1;
    trouve = i < lignes.length ? motif.exec(ligneA(lignes, i)) : null;
  }
  return { bloc: { type: 'liste', ordonnee, items }, suivant: i };
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
  while (i < lignes.length && ligneA(lignes, i).trim() !== '' && !estDebutDeBloc(ligneA(lignes, i))) {
    parties.push(ligneA(lignes, i).trim());
    i += 1;
  }
  return { bloc: { type: 'paragraphe', contenu: analyserInline(parties.join(' ')) }, suivant: i };
}

function estDebutDeBloc(ligne: string): boolean {
  return (
    ligne.startsWith(CLOTURE_CODE) ||
    MOTIF_TITRE.test(ligne) ||
    MOTIF_PUCE.test(ligne) ||
    MOTIF_NUMERO.test(ligne) ||
    MOTIF_CITATION.test(ligne) ||
    MOTIF_SEPARATEUR.test(ligne.trim())
  );
}

function lireBloc(lignes: string[], depart: number): Avance {
  const ligne = ligneA(lignes, depart);
  if (ligne.startsWith(CLOTURE_CODE)) {
    return lireCode(lignes, depart);
  }
  const titre = MOTIF_TITRE.exec(ligne);
  if (titre !== null) {
    const niveau = groupe(titre, 1).length as 1 | 2 | 3; // longueur bornée à 3 par le motif lui-même
    const contenu = analyserInline(groupe(titre, 2));
    return { bloc: { type: 'titre', niveau, contenu }, suivant: depart + 1 };
  }
  if (MOTIF_SEPARATEUR.test(ligne.trim())) {
    return { bloc: { type: 'separateur' }, suivant: depart + 1 };
  }
  if (MOTIF_PUCE.test(ligne)) {
    return lireListe(lignes, depart, false);
  }
  if (MOTIF_NUMERO.test(ligne)) {
    return lireListe(lignes, depart, true);
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
