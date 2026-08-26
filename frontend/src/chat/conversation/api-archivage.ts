/*
 * Archivage des conversations — les deux appels que `conversations-api.ts` n'expose pas encore.
 *
 * Les routes EXISTENT côté backend : `PATCH /chat/conversations/{id}` accepte `archivee`
 * (`backend/chat/routes.py`, `MajConversation`) et la liste prend `?archivees=true`
 * (`lister_conversations`). Ce fichier vit ici plutôt que dans `chat/api/` uniquement parce que la
 * refonte n'avait pas le droit d'y écrire — ces deux fonctions ont vocation à rejoindre
 * `conversations-api.ts` à la première occasion.
 */

import { getJson, patchJson } from '../api/client';
import type { ResumeConversation } from '../api/contrats';

const RACINE = '/chat/conversations';

/** Archive ou désarchive. Le résumé rendu par le backend fait foi, jamais l'état local. */
export function archiverConversation(id: string, archivee: boolean): Promise<ResumeConversation> {
  return patchJson<ResumeConversation>(`${RACINE}/${id}`, { archivee });
}

export function listerConversationsArchivees(signal?: AbortSignal): Promise<ResumeConversation[]> {
  return getJson<ResumeConversation[]>(`${RACINE}?archivees=true`, signal);
}
