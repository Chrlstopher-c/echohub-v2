/*
 * Appels du domaine `fichiers` côté backend (`/api/conversations/{id}/fichiers`, `/api/fichiers/{id}`).
 *
 * Le composeur dépose chaque pièce jointe DÈS qu'elle est choisie (collage, glisser-déposer,
 * sélection) — avant même que le message n'existe. Seul l'identifiant rendu ici part ensuite dans
 * `DemandeGeneration.fichier_ids` : aucun octet ne traverse la route de génération.
 */

import { postFormData } from './client';
import type { FichierConversation } from './contrats';

export function deposerFichier(
  conversationId: string,
  fichier: File,
  signal?: AbortSignal,
): Promise<FichierConversation> {
  const corps = new FormData();
  corps.append('fichier', fichier);
  corps.append('origine', 'utilisateur');
  return postFormData<FichierConversation>(`/conversations/${conversationId}/fichiers`, corps, signal);
}

/** URL de service d'un fichier — même route pour un artefact produit et une pièce jointe. */
export function urlFichier(fichierId: string): string {
  return `/api/fichiers/${fichierId}`;
}
