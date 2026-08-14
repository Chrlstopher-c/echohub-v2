/*
 * Client du domaine `chat` — conversations persistées et flux de génération.
 *
 * Le flux commence par un événement `debut` porteur du `message_id` de la réponse à venir :
 * l'interface peut afficher la bulle assistant avant le premier token, sans inventer d'identifiant
 * qu'il faudrait ensuite réconcilier.
 */

import { fluxJson } from './sse';
import { requeteJson } from './transport';
import type {
  ConversationDetaillee,
  CreationConversation,
  DemandeGeneration,
  EvenementFlux,
  MajConversation,
  MajReglages,
  MessageChat,
  ReglagesConversation,
  ResumeConversation,
} from './types-chat';

const RACINE = '/chat/conversations';

function chemin(conversationId: string, suffixe = ''): string {
  return `${RACINE}/${encodeURIComponent(conversationId)}${suffixe}`;
}

export function listerConversations(archivees = false, signal?: AbortSignal): Promise<readonly ResumeConversation[]> {
  return requeteJson<readonly ResumeConversation[]>(RACINE, { parametres: { archivees }, signal });
}

export function creerConversation(corps: CreationConversation = {}): Promise<ResumeConversation> {
  return requeteJson<ResumeConversation>(RACINE, { methode: 'POST', corps });
}

export function lireConversation(conversationId: string, signal?: AbortSignal): Promise<ConversationDetaillee> {
  return requeteJson<ConversationDetaillee>(chemin(conversationId), { signal });
}

export function modifierConversation(conversationId: string, patch: MajConversation): Promise<ResumeConversation> {
  return requeteJson<ResumeConversation>(chemin(conversationId), { methode: 'PATCH', corps: patch });
}

/** Arrête d'abord toute génération en cours, côté backend, avant de supprimer. */
export function supprimerConversation(conversationId: string): Promise<{ readonly supprimee: boolean }> {
  return requeteJson(chemin(conversationId), { methode: 'DELETE' });
}

export function lireReglages(conversationId: string, signal?: AbortSignal): Promise<ReglagesConversation> {
  return requeteJson<ReglagesConversation>(chemin(conversationId, '/reglages'), { signal });
}

/** Patch partiel : fusionné avec l'existant et revalidé côté backend, jamais substitué en bloc. */
export function modifierReglages(conversationId: string, patch: MajReglages): Promise<ReglagesConversation> {
  return requeteJson<ReglagesConversation>(chemin(conversationId, '/reglages'), { methode: 'PATCH', corps: patch });
}

export function listerMessages(conversationId: string, signal?: AbortSignal): Promise<readonly MessageChat[]> {
  return requeteJson<readonly MessageChat[]>(chemin(conversationId, '/messages'), { signal });
}

/** Vide l'historique en conservant la conversation et ses réglages. */
export function viderMessages(conversationId: string): Promise<{ readonly supprimes: number }> {
  return requeteJson(chemin(conversationId, '/messages'), { methode: 'DELETE' });
}

/**
 * Ouvre le flux de génération. Annuler le `signal` ferme la connexion côté navigateur ; pour
 * arrêter réellement le moteur, appeler aussi `annulerGeneration` — les deux ne font pas la même
 * chose et l'un sans l'autre laisse le backend générer dans le vide.
 */
export function genererDansConversation(
  conversationId: string,
  demande: DemandeGeneration,
  signal?: AbortSignal,
): AsyncGenerator<EvenementFlux> {
  return fluxJson<EvenementFlux>(chemin(conversationId, '/generer'), { methode: 'POST', corps: demande, signal });
}

/** `annulee` vaut `false` s'il n'y avait aucune génération en cours. */
export function annulerGeneration(conversationId: string): Promise<{ readonly annulee: boolean }> {
  return requeteJson(chemin(conversationId, '/annuler'), { methode: 'POST' });
}
