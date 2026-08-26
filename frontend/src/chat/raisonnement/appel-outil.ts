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
/*
 * La sortie porte désormais son ISSUE : `<sortie etat="echec">` quand l'appel a échoué,
 * `<sortie>` quand il a abouti. Le harnais la connaît au moment où il écrit la balise
 * (`backend/inference/harnais_outils.py`), et la transporter supprime l'interprétation qui se
 * faisait ici : l'échec était DEVINÉ en reconnaissant des préfixes de texte, ce qui tenait
 * jusqu'au premier message reformulé ou traduit.
 *
 * La forme sans attribut reste acceptée, et pas seulement par prudence : elle est déjà écrite dans
 * tous les messages enregistrés avant le 26/08/2026, et un historique relu ne doit pas changer
 * d'apparence parce que le format a évolué.
 */
const SORTIE = /<sortie(?:\s+etat="(?<etat>[a-z]+)")?>([\s\S]*?)(?:<\/sortie>|$)/;

export interface AppelOutil {
  /** Ce que le modèle a demandé — nom de l'outil et arguments, mis en forme par le backend. */
  readonly entree: string;
  /** Ce que l'outil a rendu. Vide tant que l'exécution n'a rien produit. */
  readonly sortie: string;
  /** Issue transmise par le harnais. `false` aussi tant que la sortie n'est pas close. */
  readonly echec: boolean;
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
    sortie: (sortie?.[2] ?? '').trim(),
    echec: sortie?.groups?.['etat'] === 'echec',
    termine: texte.includes('</sortie>'),
  };
}
