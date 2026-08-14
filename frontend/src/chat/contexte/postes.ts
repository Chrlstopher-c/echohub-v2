/*
 * Vocabulaire du panneau de contexte : ce que chaque poste veut dire, et comment ses chiffres
 * s'écrivent. Un seul endroit décide, pour que la barre, la légende et les infobulles ne puissent
 * pas diverger.
 *
 * Le mot du backend (`PosteContexte`) est traduit ici en libellé, couleur et explication. Aucun
 * nombre n'est calculé dans ce fichier : les tokens et les parts arrivent déjà mesurés.
 */

import type { Tone } from '../../shared/design';
import type { PosteContexte } from '../../shared/api';

/*
 * Couleur de chaque poste, prise dans la palette sémantique existante — aucune couleur inventée.
 *
 * - `raisonnement` en ambre : c'est la famille du COMPROMIS. Le raisonnement est du budget dépensé
 *   pour un texte que l'utilisateur ne relit pas ; l'ambre est exactement ce que le design réserve
 *   à ce qui dégrade sans casser.
 * - `libre` en gris : « le gris est la couleur par défaut de tout le reste ». L'espace restant
 *   n'est pas un état sain en soi — à 2 % il ne l'est plus du tout ; la santé se dit par le badge.
 * - `systeme` en orchidée : la famille du coût de contexte. Le prompt système est le coût fixe,
 *   payé à chaque tour avant qu'un mot de conversation n'existe.
 * - `utilisateur` en pervenche : la famille de l'action de l'utilisateur.
 * - `assistant` en cyan : la famille de ce qui réside dans la carte, réemployée ici pour ce que le
 *   modèle a produit. C'est le maillon le plus faible de cette correspondance — il mériterait un
 *   token dédié plutôt qu'un emprunt à la famille mémoire.
 */
export const TONE_POSTE: Record<PosteContexte, Tone> = {
  systeme: 'kv',
  utilisateur: 'accent',
  assistant: 'vram',
  raisonnement: 'caution',
  libre: 'neutral',
};

export const LIBELLE_POSTE: Record<PosteContexte, string> = {
  systeme: 'Prompt système',
  utilisateur: 'Vos messages',
  assistant: 'Réponses',
  raisonnement: 'Raisonnement',
  libre: 'Libre',
};

export const DESCRIPTION_POSTE: Record<PosteContexte, string> = {
  systeme: "Instructions renvoyées au modèle à chaque tour, avant tout message.",
  utilisateur: 'Ce que vous avez écrit, tel que le modèle le relit à chaque tour.',
  assistant: 'Réponses visibles du modèle, hors blocs de raisonnement.',
  raisonnement: "Blocs <think> conservés dans l'historique : ils repartent au modèle et coûtent "
    + 'donc du contexte, sans être relus par vous.',
  libre: "Ce qu'il reste dans la fenêtre servie par le moteur.",
};

const ENTIER = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
const POURCENT = new Intl.NumberFormat('fr-FR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function formaterTokens(tokens: number): string {
  return ENTIER.format(tokens);
}

/** Une décimale fixe : le chiffre ne change pas de largeur quand il passe de 9,9 à 10,0. */
export function formaterPart(fraction: number): string {
  return `${POURCENT.format(fraction * 100)} %`;
}
