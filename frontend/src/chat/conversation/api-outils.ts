/*
 * Sélection des outils d'une conversation — codée contre le CONTRAT PROPOSÉ au backend (rapport
 * de refonte), qui n'existe pas encore côté serveur :
 *
 *   GET  /chat/outils                          -> OutilDisponible[]   (catalogue + coût mesuré)
 *   GET  /chat/conversations/{id}/outils       -> { outils_actifs: string[] | null }
 *   PUT  /chat/conversations/{id}/outils       <- { outils_actifs: string[] | null }
 *
 * `null` signifie « tous les outils », le défaut historique — distinct de `[]`, qui coupe tout.
 * Tant que les routes manquent, chaque appel échoue en 404 : le hook le traduit en mode dégradé
 * visible (sélection non persistée) au lieu de le masquer.
 */

import { getJson, patchJson } from '../api/client';
import type { OutilDisponible } from './outils-catalogue';

export interface SelectionOutils {
  readonly outils_actifs: readonly string[] | null;
}

export function listerOutilsDisponibles(signal?: AbortSignal): Promise<OutilDisponible[]> {
  return getJson<OutilDisponible[]>('/chat/outils', signal);
}

export function lireSelectionOutils(conversationId: string, signal?: AbortSignal): Promise<SelectionOutils> {
  return getJson<SelectionOutils>(`/chat/conversations/${conversationId}/outils`, signal);
}

export function ecrireSelectionOutils(
  conversationId: string,
  outilsActifs: readonly string[] | null,
): Promise<SelectionOutils> {
  // PATCH et non PUT : `client.ts` n'expose pas de PUT, et la sémantique — remplacer la seule
  // clé `outils_actifs` — est celle d'une mise à jour partielle de la conversation.
  return patchJson<SelectionOutils>(`/chat/conversations/${conversationId}/outils`, {
    outils_actifs: outilsActifs,
  });
}
