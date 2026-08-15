/*
 * Appels du domaine `fichiers` côté backend (`/api/conversations/{id}/fichiers`, `/api/fichiers/{id}`).
 *
 * Le composeur dépose chaque pièce jointe DÈS qu'elle est choisie (collage, glisser-déposer,
 * sélection) — avant même que le message n'existe. Seul l'identifiant rendu ici part ensuite dans
 * `DemandeGeneration.fichier_ids` : aucun octet ne traverse la route de génération.
 */

import { lireErreur, postFormData } from './client';
import { journal } from './journal';
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

/**
 * Contenu textuel d'un fichier — pour l'afficher en code, ou l'injecter dans un aperçu HTML.
 * Passe par `fetch` directement plutôt que par `requete<T>` (`client.ts`) : la réponse n'est pas
 * du JSON, c'est le fichier lui-même, servi tel quel par `FileResponse` (`backend/fichiers/routes.py`).
 */
export async function chargerTexteFichier(fichierId: string, signal?: AbortSignal): Promise<string> {
  let reponse: Response;
  try {
    reponse = await fetch(urlFichier(fichierId), { signal });
  } catch (cause) {
    journal.erreur(`lecture du fichier ${fichierId} échouée`, cause);
    throw cause;
  }
  if (!reponse.ok) {
    throw await lireErreur(reponse);
  }
  return reponse.text();
}
