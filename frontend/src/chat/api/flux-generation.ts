/*
 * Lecture du flux SSE de génération.
 *
 * `fetch` + `ReadableStream` plutôt que `EventSource` pour deux raisons : `EventSource` ne sait pas
 * émettre un POST (le corps porte le message et les paramètres), et il ne s'annule pas proprement —
 * or l'annulation en cours de génération est une exigence de l'écran.
 *
 * Le backend émet à la fois `event:` et un champ `type` dans la charge JSON ; on parse le JSON, ce
 * qui rend la lecture indépendante du nom d'événement.
 */

import type { DemandeGeneration, EvenementFlux } from './contrats';
import { ErreurApi } from './client';
import { journal } from './journal';

/*
 * Borne dure du nombre de lectures du flux. Le backend plafonne `max_tokens` à 262 144 et émet un
 * fragment par token : au-delà d'un million de lectures, le flux ne se comporte plus comme un flux
 * de génération et on préfère rompre plutôt que boucler indéfiniment.
 */
const LECTURES_MAX = 1_000_000;

const SEPARATEUR_TRAME = '\n\n';
const PREFIXE_DONNEES = 'data:';

export interface RappelsFlux {
  onEvenement: (evenement: EvenementFlux) => void;
}

function extraireCharge(trame: string): string | null {
  for (const ligne of trame.split('\n')) {
    if (ligne.startsWith(PREFIXE_DONNEES)) {
      return ligne.slice(PREFIXE_DONNEES.length).trim();
    }
  }
  return null;
}

function traiterTrame(trame: string, rappels: RappelsFlux): void {
  const charge = extraireCharge(trame);
  if (charge === null || charge === '') {
    return;
  }
  try {
    // Même justification que dans `client.ts` : le contrat est décrit par `contrats.ts`.
    rappels.onEvenement(JSON.parse(charge) as EvenementFlux);
  } catch (cause) {
    journal.avertissement('trame SSE illisible, ignorée', cause);
  }
}

/** Consomme les trames complètes du tampon et rend le reliquat incomplet. */
function consommerTrames(tampon: string, rappels: RappelsFlux): string {
  const morceaux = tampon.split(SEPARATEUR_TRAME);
  const reliquat = morceaux.pop() ?? '';
  for (const trame of morceaux) {
    traiterTrame(trame, rappels);
  }
  return reliquat;
}

async function drainer(corps: ReadableStream<Uint8Array>, rappels: RappelsFlux): Promise<void> {
  const lecteur = corps.getReader();
  const decodeur = new TextDecoder();
  let tampon = '';
  try {
    for (let lecture = 0; lecture < LECTURES_MAX; lecture += 1) {
      const { done, value } = await lecteur.read();
      if (done) {
        consommerTrames(`${tampon}${SEPARATEUR_TRAME}`, rappels);
        return;
      }
      tampon = consommerTrames(tampon + decodeur.decode(value, { stream: true }), rappels);
    }
    journal.avertissement('flux de génération interrompu : borne de lectures atteinte');
  } finally {
    lecteur.releaseLock();
  }
}

/**
 * Ouvre le flux et rend la main quand il se ferme. L'annulation passe par `signal` ; l'échec
 * d'ouverture reste une `ErreurApi` (le statut HTTP est encore disponible à ce moment), alors qu'un
 * échec ultérieur arrive sous forme d'événement `erreur` dans le flux lui-même.
 */
export async function ouvrirFluxGeneration(
  conversationId: string,
  demande: DemandeGeneration,
  rappels: RappelsFlux,
  signal: AbortSignal,
): Promise<void> {
  const reponse = await fetch(`/api/chat/conversations/${conversationId}/generer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(demande),
    signal,
  });
  if (!reponse.ok || reponse.body === null) {
    journal.erreur(`ouverture du flux refusée (${reponse.status})`);
    throw new ErreurApi(
      reponse.status,
      'flux_refuse',
      'La génération n’a pas pu démarrer.',
      'Vérifier qu’un modèle est chargé et qu’aucune génération n’est déjà en cours.',
    );
  }
  await drainer(reponse.body, rappels);
}
