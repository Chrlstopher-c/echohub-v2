/*
 * Appels du domaine `chat` côté backend (`/api/chat`). Une fonction par route, rien de plus :
 * la logique d'écran vit dans les hooks, pas ici.
 */

import { deleteJson, getJson, patchJson, postJson } from './client';
import type {
  ConversationDetaillee,
  MajReglages,
  MessageChat,
  ReglagesConversation,
  ResumeConversation,
} from './contrats';

const RACINE = '/chat/conversations';

export function listerConversations(signal?: AbortSignal): Promise<ResumeConversation[]> {
  return getJson<ResumeConversation[]>(RACINE, signal);
}

export function creerConversation(titre: string, modeleId: string | null): Promise<ResumeConversation> {
  return postJson<ResumeConversation>(RACINE, { titre, modele_id: modeleId });
}

export function lireConversation(id: string, signal?: AbortSignal): Promise<ConversationDetaillee> {
  return getJson<ConversationDetaillee>(`${RACINE}/${id}`, signal);
}

export function supprimerConversation(id: string): Promise<{ supprimee: boolean }> {
  return deleteJson<{ supprimee: boolean }>(`${RACINE}/${id}`);
}

export function listerMessages(id: string, signal?: AbortSignal): Promise<MessageChat[]> {
  return getJson<MessageChat[]>(`${RACINE}/${id}/messages`, signal);
}

export function ecrireReglages(id: string, patch: MajReglages): Promise<ReglagesConversation> {
  return patchJson<ReglagesConversation>(`${RACINE}/${id}/reglages`, patch);
}

/** Demande l'arrêt côté serveur. `annulee: false` signifie qu'il n'y avait rien à arrêter. */
export function annulerGeneration(id: string): Promise<{ annulee: boolean }> {
  return postJson<{ annulee: boolean }>(`${RACINE}/${id}/annuler`, {});
}
