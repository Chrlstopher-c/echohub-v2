/*
 * Coloration syntaxique : découpage d'un extrait de code en jetons typés.
 *
 * Arbitrage de couleur (DESIGN.md, « toute couleur est un mot du vocabulaire ») : la palette
 * produit nomme des états et des ressources, pas des catégories lexicales. Peindre un mot-clé en
 * rouge « critique » mentirait. La coloration reste donc en niveaux de gris — la hiérarchie du
 * texte — avec l'accent comme unique teinte, réservée aux mots-clés du langage.
 *
 * Le découpage est volontairement grossier : il sert la lecture d'un extrait dans une conversation,
 * pas l'édition. Un langage inconnu retombe sur les règles communes (chaînes, nombres, commentaires).
 */

export type TypeJeton = 'texte' | 'motcle' | 'chaine' | 'commentaire' | 'nombre';

export interface Jeton {
  type: TypeJeton;
  texte: string;
}

const MOTS_CLES_COMMUNS = [
  'if', 'else', 'for', 'while', 'return', 'break', 'continue', 'import', 'from', 'class', 'try',
  'catch', 'except', 'finally', 'raise', 'throw', 'new', 'true', 'false', 'null', 'None', 'True',
  'False', 'and', 'or', 'not', 'in', 'is', 'as', 'with', 'yield', 'await', 'async',
];

const MOTS_CLES_PAR_FAMILLE: Record<string, readonly string[] | undefined> = {
  ts: ['const', 'let', 'var', 'function', 'interface', 'type', 'export', 'extends', 'implements', 'readonly'],
  py: ['def', 'elif', 'lambda', 'global', 'nonlocal', 'pass', 'self', 'assert', 'del'],
  sh: ['echo', 'fi', 'then', 'do', 'done', 'esac', 'case', 'local', 'export', 'source'],
  rs: ['fn', 'let', 'mut', 'impl', 'struct', 'enum', 'pub', 'match', 'use', 'trait'],
};

const FAMILLES: Record<string, string | undefined> = {
  ts: 'ts', tsx: 'ts', js: 'ts', jsx: 'ts', json: 'ts',
  py: 'py', python: 'py',
  sh: 'sh', bash: 'sh', zsh: 'sh', shell: 'sh', console: 'sh',
  rs: 'rs', rust: 'rs',
};

/* Ordre significatif : commentaire et chaîne d'abord, sinon un « # » dans une chaîne couperait tout. */
const COMMENTAIRE = String.raw`(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/)`;
const CHAINE_DOUBLE = String.raw`"(?:\\.|[^"\\])*"`;
const CHAINE_SIMPLE = String.raw`'(?:\\.|[^'\\])*'`;
const CHAINE_GABARIT = '`(?:\\\\.|[^`\\\\])*`';
const CHAINE = `(${CHAINE_DOUBLE}|${CHAINE_SIMPLE}|${CHAINE_GABARIT})`;
const NOMBRE = String.raw`(\b\d[\d_]*(?:\.\d+)?\b)`;
const IDENTIFIANT = String.raw`([A-Za-z_][A-Za-z0-9_]*)`;

const MOTIF_JETON = new RegExp([COMMENTAIRE, CHAINE, NOMBRE, IDENTIFIANT].join('|'), 'g');

function motsCles(langage: string): ReadonlySet<string> {
  const famille = FAMILLES[langage.toLowerCase()];
  const specifiques = famille === undefined ? [] : MOTS_CLES_PAR_FAMILLE[famille] ?? [];
  return new Set([...MOTS_CLES_COMMUNS, ...specifiques]);
}

function jetonDepuisCapture(trouve: RegExpExecArray, cles: ReadonlySet<string>): Jeton {
  // Voir `parseur.ts` : un groupe non apparié vaut `undefined`, que le type de la lib ignore.
  const groupes: Array<string | undefined> = trouve;
  if (groupes[1] !== undefined) {
    return { type: 'commentaire', texte: groupes[1] };
  }
  if (groupes[2] !== undefined) {
    return { type: 'chaine', texte: groupes[2] };
  }
  if (groupes[3] !== undefined) {
    return { type: 'nombre', texte: groupes[3] };
  }
  const mot = groupes[4] ?? '';
  return { type: cles.has(mot) ? 'motcle' : 'texte', texte: mot };
}

/** Découpe le source en jetons contigus : leur concaténation redonne le texte d'origine. */
export function colorier(source: string, langage: string): Jeton[] {
  const cles = motsCles(langage);
  const jetons: Jeton[] = [];
  let curseur = 0;
  MOTIF_JETON.lastIndex = 0;
  let trouve = MOTIF_JETON.exec(source);
  while (trouve !== null) {
    if (trouve.index > curseur) {
      jetons.push({ type: 'texte', texte: source.slice(curseur, trouve.index) });
    }
    jetons.push(jetonDepuisCapture(trouve, cles));
    curseur = trouve.index + trouve[0].length;
    trouve = MOTIF_JETON.exec(source);
  }
  if (curseur < source.length) {
    jetons.push({ type: 'texte', texte: source.slice(curseur) });
  }
  return jetons;
}

/** Classe Tailwind de chaque type de jeton — une seule teinte, le reste en niveaux de gris. */
export const CLASSE_JETON: Record<TypeJeton, string> = {
  texte: 'text-text',
  motcle: 'text-accent',
  chaine: 'text-text-2',
  commentaire: 'text-text-3',
  nombre: 'text-text-2',
};
