/*
 * Découpe d'un bloc d'outil en ce qui a été DEMANDÉ et ce qui a été RENDU.
 *
 * Le backend encadre les deux parties (`backend/inference/__init__.py`) et les émet à des instants
 * différents : l'entrée part avant l'exécution, la sortie après. Ce module doit donc rester
 * tolérant à l'inachevé — pendant que l'outil travaille, seule l'entrée existe, et c'est
 * précisément ce qu'il faut afficher pour que l'attente ne soit pas muette.
 *
 * Fonction pure, testable sans rendu.
 */

const ENTREE = /<entree>([\s\S]*?)(?:<\/entree>|$)/;
const SORTIE = /<sortie>([\s\S]*?)(?:<\/sortie>|$)/;

export interface AppelOutil {
  /** Ce que le modèle a demandé — nom de l'outil et arguments, mis en forme par le backend. */
  readonly entree: string;
  /** Ce que l'outil a rendu. Vide tant que l'exécution n'a rien produit. */
  readonly sortie: string;
  /** `false` tant que la sortie n'est pas close : l'outil est encore en train de travailler. */
  readonly termine: boolean;
}

/**
 * Rend `null` quand le texte ne porte aucune des deux balises — un bloc d'une version antérieure,
 * ou un contenu qu'on ne doit pas prétendre comprendre. L'appelant affiche alors le texte tel quel
 * plutôt qu'une structure inventée.
 */
export function decouperAppel(texte: string): AppelOutil | null {
  const entree = ENTREE.exec(texte);
  const sortie = SORTIE.exec(texte);
  if (entree === null && sortie === null) {
    return null;
  }
  return {
    entree: (entree?.[1] ?? '').trim(),
    sortie: (sortie?.[1] ?? '').trim(),
    termine: texte.includes('</sortie>'),
  };
}
