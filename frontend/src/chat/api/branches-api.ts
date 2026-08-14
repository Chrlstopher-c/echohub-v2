/*
 * Branches de conversation (`/api/chat/conversations/{id}/branche`).
 *
 * Séparé de `conversations-api.ts` parce que ces routes répondent à une autre question : non pas
 * « que contient cette conversation » mais « quel chemin de l'arbre est actuellement affiché, et
 * quels frères a chacun de ses messages ». Le chemin n'est jamais reconstruit côté navigateur —
 * il est lu, y compris après une bascule.
 */

import { getJson, postJson } from './client';
import type { ActivationBranche, EtatBranche } from './contrats';

const RACINE = '/chat/conversations';

/** Vue courante : chemin racine→feuille, plus les variantes de chacun de ses messages. */
export function lireBranche(id: string, signal?: AbortSignal): Promise<EtatBranche> {
  return getJson<EtatBranche>(`${RACINE}/${id}/branche`, signal);
}

/**
 * Bascule la vue sur la branche contenant `messageId`, en redescendant jusqu'à sa variante la plus
 * récente. C'est l'appel des flèches « ‹ 2 / 3 › ». Rien n'est détruit : la branche qu'on quitte
 * reste entière côté serveur, et un second appel y ramène.
 */
export function activerBranche(id: string, messageId: string): Promise<EtatBranche> {
  const corps: ActivationBranche = { message_id: messageId };
  return postJson<EtatBranche>(`${RACINE}/${id}/branche`, corps);
}
