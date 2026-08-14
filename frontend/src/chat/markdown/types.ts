/*
 * Formes de l'arbre Markdown — le contrat entre l'analyse (`parseur.ts`) et le rendu
 * (`RenduMarkdown.tsx`). Isolées ici pour que le rendu n'importe que des types, jamais la
 * machinerie qui les produit, et pour qu'aucun cycle d'import n'apparaisse entre les lecteurs.
 *
 * Rien dans cet arbre n'est du HTML : uniquement des chaînes brutes que React échappera. C'est la
 * raison d'être de l'analyseur maison, énoncée dans `parseur.ts` — ne pas la contredire ici.
 */

export type SegmentInline =
  | { type: 'texte'; texte: string }
  | { type: 'fort'; texte: string }
  | { type: 'emphase'; texte: string }
  | { type: 'code'; texte: string }
  | { type: 'lien'; texte: string; href: string };

/* Six niveaux : les modèles descendent couramment à `####` pour détailler un sous-point, et un
 * titre non reconnu réapparaîtrait tel quel (« #### Étape 2 ») dans le texte rendu. */
export type NiveauTitre = 1 | 2 | 3 | 4 | 5 | 6;

export type Alignement = 'gauche' | 'centre' | 'droite';

export interface ItemListe {
  contenu: SegmentInline[];
  /* `null` plutôt qu'une liste vide : « pas de sous-liste » et « sous-liste sans item » sont deux
   * états différents, et seul le premier doit se rendre sans balise imbriquée. */
  sousListe: BlocListe | null;
}

export interface BlocListe {
  type: 'liste';
  ordonnee: boolean;
  items: ItemListe[];
}

export interface BlocTableau {
  type: 'tableau';
  entetes: SegmentInline[][];
  /* Un alignement par colonne, lu dans la ligne de délimiteurs (`:---`, `---:`, `:---:`). Jamais
   * déduit du contenu des cellules : un alignement non déclaré vaut « gauche ». */
  alignements: Alignement[];
  lignes: SegmentInline[][][];
}

export type BlocMarkdown =
  | { type: 'titre'; niveau: NiveauTitre; contenu: SegmentInline[] }
  | { type: 'paragraphe'; contenu: SegmentInline[] }
  | { type: 'code'; langage: string; texte: string; complet: boolean }
  | BlocListe
  | BlocTableau
  | { type: 'citation'; contenu: SegmentInline[] }
  | { type: 'separateur' };

/** Lecture d'un bloc : ce qui a été produit, et l'index de la ligne où reprendre. */
export interface Avance {
  bloc: BlocMarkdown;
  suivant: number;
}

/** Même contrat, restreint aux listes : l'imbrication a besoin du type précis pour se rattacher. */
export interface AvanceListe {
  bloc: BlocListe;
  suivant: number;
}
