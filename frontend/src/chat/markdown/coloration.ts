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
 *
 * HTML et CSS (plan d'exécution, lot L3) suivent un chemin séparé, `_colorierBalise`/`_colorierCss`
 * : une balise (`<div class="x">`) ou un sélecteur (`.classe { couleur: rouge; }`) n'a pas
 * d'identifiant isolé à comparer à une liste de mots-clés, mais une STRUCTURE — chevrons, noms de
 * balise ou de propriété, accolades. Toujours sans dépendance : ce fichier reste écrit à la main.
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
  html: 'html', htm: 'html', xml: 'html', svg: 'html',
  css: 'css',
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

/* Balise ouvrante/fermante et chevron seul (`>`, `/>`) ; les attributs se lisent dans le texte
 * entre deux balises et n'ont pas besoin d'un groupe dédié — ils tombent dans `texte`, comme la
 * ponctuation, ce qui reste lisible : seule la structure des balises et des chaînes est éclairée. */
const BALISE_HTML = String.raw`(<\/?[A-Za-z][A-Za-z0-9-]*|\/?>)`;
const MOTIF_HTML = new RegExp([COMMENTAIRE, CHAINE, BALISE_HTML].join('|'), 'g');

const PROPRIETE_CSS = String.raw`([A-Za-z-]+(?=\s*:))`;
const SELECTEUR_CSS = String.raw`([.#]?[A-Za-z][A-Za-z0-9_-]*(?=\s*[{,]))`;
const MOTIF_CSS = new RegExp([COMMENTAIRE, CHAINE, PROPRIETE_CSS, SELECTEUR_CSS, NOMBRE].join('|'), 'g');

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

/** Assemble les jetons trouvés par un motif donné avec le texte qui les sépare, dans l'ordre. */
function _decouper(source: string, motif: RegExp, versJeton: (trouve: RegExpExecArray) => Jeton): Jeton[] {
  const jetons: Jeton[] = [];
  let curseur = 0;
  motif.lastIndex = 0;
  let trouve = motif.exec(source);
  while (trouve !== null) {
    if (trouve.index > curseur) {
      jetons.push({ type: 'texte', texte: source.slice(curseur, trouve.index) });
    }
    jetons.push(versJeton(trouve));
    curseur = trouve.index + trouve[0].length;
    trouve = motif.exec(source);
  }
  if (curseur < source.length) {
    jetons.push({ type: 'texte', texte: source.slice(curseur) });
  }
  return jetons;
}

function _jetonHtml(trouve: RegExpExecArray): Jeton {
  const groupes: Array<string | undefined> = trouve;
  if (groupes[1] !== undefined) {
    return { type: 'commentaire', texte: groupes[1] };
  }
  if (groupes[2] !== undefined) {
    return { type: 'chaine', texte: groupes[2] };
  }
  return { type: 'motcle', texte: groupes[3] ?? '' };
}

function _jetonCss(trouve: RegExpExecArray): Jeton {
  const groupes: Array<string | undefined> = trouve;
  if (groupes[1] !== undefined) {
    return { type: 'commentaire', texte: groupes[1] };
  }
  if (groupes[2] !== undefined) {
    return { type: 'chaine', texte: groupes[2] };
  }
  if (groupes[3] !== undefined) {
    return { type: 'motcle', texte: groupes[3] }; // propriété
  }
  if (groupes[4] !== undefined) {
    return { type: 'motcle', texte: groupes[4] }; // sélecteur
  }
  return { type: 'nombre', texte: groupes[5] ?? '' };
}

/** Découpe le source en jetons contigus : leur concaténation redonne le texte d'origine. */
export function colorier(source: string, langage: string): Jeton[] {
  const famille = FAMILLES[langage.toLowerCase()];
  if (famille === 'html') {
    return _decouper(source, MOTIF_HTML, _jetonHtml);
  }
  if (famille === 'css') {
    return _decouper(source, MOTIF_CSS, _jetonCss);
  }
  const cles = motsCles(langage);
  return _decouper(source, MOTIF_JETON, (trouve) => jetonDepuisCapture(trouve, cles));
}

/** Classe Tailwind de chaque type de jeton — une seule teinte, le reste en niveaux de gris. */
export const CLASSE_JETON: Record<TypeJeton, string> = {
  texte: 'text-text',
  motcle: 'text-accent',
  chaine: 'text-text-2',
  commentaire: 'text-text-3',
  nombre: 'text-text-2',
};
