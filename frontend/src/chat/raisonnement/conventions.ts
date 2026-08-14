/*
 * Conventions de balisage du raisonnement.
 *
 * Une seule est CONSTATÉE sur les modèles servis par le projet : `<think>` / `</think>` (famille
 * Qwen3, DeepSeek-R1). Le backend la reconnaît littéralement dans
 * `backend/inference/engines_adapters/contrat.py` (`BALISE_RAISONNEMENT_OUVRANTE`), et c'est de là
 * que vient le poste « raisonnement » du panneau de contexte.
 *
 * La liste est le point d'extension : ajouter une convention observée = ajouter une entrée, rien
 * d'autre à toucher. Aucune n'est ajoutée « au cas où » — un format non constaté découperait des
 * réponses sur une balise imaginaire, et ferait disparaître du texte réel de l'écran.
 *
 * Toute entrée ajoutée ici doit l'être aussi côté backend : sinon le texte serait masqué à l'écran
 * tout en restant compté dans le poste « réponses » du contexte, et les deux affichages mentiraient
 * l'un par rapport à l'autre.
 */

export interface ConventionRaisonnement {
  /** Nom court, repris tel quel dans l'interface quand plusieurs conventions coexistent. */
  readonly nom: string;
  readonly ouvrante: string;
  readonly fermante: string;
}

export const CONVENTIONS_RAISONNEMENT: readonly ConventionRaisonnement[] = [
  { nom: 'think', ouvrante: '<think>', fermante: '</think>' },
];
