/*
 * Interface publique du module `markdown` — seul point d'import autorisé depuis le reste du
 * domaine `chat` (`conversation/`, `raisonnement/`).
 *
 * Le module expose un composant et l'analyse qui le nourrit. Ni les lecteurs de blocs, ni la
 * coloration syntaxique, ni les formes intermédiaires de l'arbre ne sortent d'ici : ce sont des
 * détails d'implémentation, remplaçables sans prévenir tant que le texte rendu ne change pas.
 */

export { RenduMarkdown, type RenduMarkdownProps } from './RenduMarkdown';
export { analyserMarkdown } from './parseur';
export type { BlocMarkdown, SegmentInline } from './types';
