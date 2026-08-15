/*
 * Langage et aperçu d'un artefact — dérivés du nom affiché et du type MIME, jamais d'un champ que
 * le modèle choisirait lui-même : le nom fourni est une entrée non fiable (même règle que
 * `backend/fichiers/politique.py`, qui ne dérive jamais l'extension écrite sur le disque du nom
 * fourni). Ici l'enjeu n'est que l'affichage — coloration et aperçu — mais la même prudence tient :
 * une extension mensongère ne doit produire, au pire, qu'une mauvaise coloration, jamais un aperçu
 * exécuté à tort.
 *
 * Règle de l'opérateur (plan d'exécution, 2.6) : seul HTML a un aperçu qui ait un sens ici — une
 * page se rend, du code se lit. Pour tout le reste, l'interrupteur reste PRÉSENT mais désactivé,
 * avec sa raison au survol : un contrôle manquant se lit comme un bug, un contrôle expliqué comme
 * une décision.
 */

export interface DescriptionLangage {
  readonly langage: string;
  readonly apercuPossible: boolean;
  /** Raison affichée au survol de l'interrupteur désactivé — jamais vide dans ce cas. */
  readonly raisonAbsenceApercu: string;
}

const RAISON_PYTHON =
  "Le code Python s'exécute, il ne se prévisualise pas : c'est le modèle qui en montre le résultat.";
const RAISON_GENERIQUE = "Aucun aperçu n'a de sens pour ce type de fichier : ce texte se lit, il ne se rend pas.";

const LANGAGE_PAR_MIME: Record<string, string> = {
  'text/x-python': 'py',
  'application/x-python': 'py',
  'text/html': 'html',
  'text/css': 'css',
  'application/json': 'json',
  'text/csv': 'csv',
  'text/markdown': 'md',
  'text/plain': 'txt',
  'application/javascript': 'js',
  'text/javascript': 'js',
  'application/xml': 'xml',
  'text/xml': 'xml',
};

function langageDepuisNom(nom: string): string | null {
  const correspondance = /\.([A-Za-z0-9]+)$/.exec(nom);
  const extension = correspondance?.[1];
  return extension !== undefined ? extension.toLowerCase() : null;
}

/** Description complète d'un artefact affiché : langage de coloration, et sort de l'aperçu. */
export function decrireLangage(nomAffiche: string, typeMime: string): DescriptionLangage {
  const langage = langageDepuisNom(nomAffiche) ?? LANGAGE_PAR_MIME[typeMime] ?? 'txt';
  if (langage === 'html' || langage === 'htm') {
    return { langage: 'html', apercuPossible: true, raisonAbsenceApercu: '' };
  }
  const raison = langage === 'py' ? RAISON_PYTHON : RAISON_GENERIQUE;
  return { langage, apercuPossible: false, raisonAbsenceApercu: raison };
}
