/*
 * Transport HTTP du domaine chat : un seul endroit sait construire une URL, lire une erreur du
 * backend et la transformer en objet exploitable.
 *
 * Les erreurs métier du backend voyagent dans `detail` sous la forme `{code, message, remediation}`
 * (cf. `core.errors`). Les aplatir ici évite que chaque écran réinvente sa lecture d'erreur — et
 * surtout que la remédiation, qui est le seul texte utile à l'utilisateur, soit perdue en route.
 */

import { journal } from './journal';

const BASE_API = '/api';

export class ErreurApi extends Error {
  readonly code: string;
  readonly remediation: string;
  readonly statut: number;

  constructor(statut: number, code: string, message: string, remediation: string) {
    super(message);
    this.name = 'ErreurApi';
    this.statut = statut;
    this.code = code;
    this.remediation = remediation;
  }
}

interface DetailErreur {
  code?: string;
  message?: string;
  remediation?: string;
}

function estObjet(valeur: unknown): valeur is Record<string, unknown> {
  return typeof valeur === 'object' && valeur !== null;
}

function texteOuVide(valeur: unknown): string {
  return typeof valeur === 'string' ? valeur : '';
}

/** Extrait `{code, message, remediation}` quelle que soit la profondeur où FastAPI l'a rangé. */
function extraireDetail(charge: unknown): DetailErreur {
  if (!estObjet(charge)) {
    return {};
  }
  // Accès indexé et non par propriété : la charge vient du réseau, ses clés ne sont pas connues
  // du typage. `noPropertyAccessFromIndexSignature` impose de le dire, et il a raison de le faire.
  const detail = charge['detail'];
  const interne = estObjet(detail) ? detail : charge;
  return {
    code: texteOuVide(interne['code']),
    message: texteOuVide(interne['message']),
    remediation: texteOuVide(interne['remediation']),
  };
}

async function lireErreur(reponse: Response): Promise<ErreurApi> {
  let detail: DetailErreur = {};
  try {
    detail = extraireDetail(await reponse.json());
  } catch (cause) {
    // Réponse d'erreur non-JSON (nginx, proxy) : le statut reste la seule information fiable.
    journal.avertissement(`réponse d'erreur illisible sur ${reponse.url}`, cause);
  }
  const message = detail.message !== undefined && detail.message !== '' ? detail.message : reponse.statusText;
  return new ErreurApi(reponse.status, detail.code ?? '', message, detail.remediation ?? '');
}

async function requete<T>(chemin: string, init: RequestInit): Promise<T> {
  let reponse: Response;
  try {
    reponse = await fetch(`${BASE_API}${chemin}`, init);
  } catch (cause) {
    journal.erreur(`appel réseau échoué : ${chemin}`, cause);
    throw new ErreurApi(0, 'reseau_indisponible', 'Le backend est injoignable.', 'Vérifier que le service tourne.');
  }
  if (!reponse.ok) {
    const erreur = await lireErreur(reponse);
    journal.erreur(`${chemin} → ${reponse.status} ${erreur.code}`, erreur.message);
    throw erreur;
  }
  // Le contrat serveur est décrit par `contrats.ts` ; une validation de schéma au runtime
  // appartiendrait à une couche dédiée, hors périmètre du MVP. Le cast est donc assumé ici, et
  // ici seulement : aucun autre fichier du domaine ne manipule de réponse non typée.
  const charge: unknown = await reponse.json();
  return charge as T;
}

const ENTETES_JSON: Record<string, string> = { 'Content-Type': 'application/json' };

export function getJson<T>(chemin: string, signal?: AbortSignal): Promise<T> {
  return requete<T>(chemin, { method: 'GET', signal });
}

export function postJson<T>(chemin: string, corps: unknown, signal?: AbortSignal): Promise<T> {
  return requete<T>(chemin, {
    method: 'POST',
    headers: ENTETES_JSON,
    body: JSON.stringify(corps),
    signal,
  });
}

export function patchJson<T>(chemin: string, corps: unknown, signal?: AbortSignal): Promise<T> {
  return requete<T>(chemin, {
    method: 'PATCH',
    headers: ENTETES_JSON,
    body: JSON.stringify(corps),
    signal,
  });
}

export function deleteJson<T>(chemin: string, signal?: AbortSignal): Promise<T> {
  return requete<T>(chemin, { method: 'DELETE', signal });
}

/** Message affichable d'une erreur quelconque — évite un `instanceof` répété dans chaque hook. */
export function messageErreur(cause: unknown): string {
  if (cause instanceof ErreurApi) {
    return cause.remediation !== '' ? `${cause.message} ${cause.remediation}` : cause.message;
  }
  if (cause instanceof Error) {
    return cause.message;
  }
  return 'Erreur inconnue.';
}
