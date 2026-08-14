/*
 * Analyse du niveau inline : code, gras, emphase, liens.
 *
 * Un motif unique parcouru une seule fois, plutôt qu'une succession de remplacements : le texte
 * hors motif reste du texte brut, ce qui garantit qu'aucun caractère reçu n'est perdu — la
 * concaténation des segments redonne exactement la source.
 */

import type { SegmentInline } from './types';

/* `_souligné_` n'est volontairement pas reconnu : il découperait `nom_de_variable` en emphase au
 * milieu d'un identifiant, cas bien plus fréquent dans une réponse technique que l'italique. */
const MOTIF_INLINE = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*\n]+)\*|\[([^\]]+)\]\(([^)\s]+)\)/g;

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

/**
 * Découpe une ligne en segments typés. Un marqueur ouvert mais pas encore refermé (`**gras` en
 * cours de streaming) ne correspond à aucun motif : il ressort en texte, il ne disparaît pas.
 */
export function analyserInline(source: string): SegmentInline[] {
  const segments: SegmentInline[] = [];
  let curseur = 0;
  MOTIF_INLINE.lastIndex = 0;
  let trouve = MOTIF_INLINE.exec(source);
  // Borne : `lastIndex` avance strictement à chaque correspondance, le motif n'accepte pas le vide.
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
