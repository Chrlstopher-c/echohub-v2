/*
 * Accès HTTP du domaine `models`.
 *
 * Le client vit DANS le domaine : `shared/` n'expose pas de client API, et un domaine ne dépend
 * pas d'un module qui n'existe pas. La ressemblance avec celui du domaine `system` est une
 * duplication accidentelle assumée — deux domaines qui appellent HTTP, pas une règle métier
 * partagée. Le jour où `shared/api` existera, les deux disparaîtront ensemble.
 */

const RACINE_API = '/api';

/** Erreur métier telle que le backend la sérialise (`EchoHubError.to_dict`). */
export interface DetailErreurApi {
  code: string;
  message: string;
  remediation: string;
}

export class ErreurApi extends Error {
  readonly statut: number;
  readonly code: string;
  readonly remediation: string;

  constructor(statut: number, code: string, message: string, remediation: string) {
    super(message);
    this.name = 'ErreurApi';
    this.statut = statut;
    this.code = code;
    this.remediation = remediation;
  }
}

export const journal = {
  /** Pas de pino dans un bundle navigateur : la console est le seul puits disponible ici. */
  erreur(contexte: string, cause: unknown): void {
    console.error(`[models] ${contexte}`, cause);
  },
};

function champ(valeur: object, nom: string): unknown {
  // Cast justifié : la garde `hasOwnProperty` précède l'accès, aucune propriété n'est inventée.
  return Object.prototype.hasOwnProperty.call(valeur, nom) ? (valeur as Record<string, unknown>)[nom] : undefined;
}

function estDetailErreur(valeur: unknown): valeur is DetailErreurApi {
  if (valeur === null || typeof valeur !== 'object') {
    return false;
  }
  return typeof champ(valeur, 'message') === 'string' && typeof champ(valeur, 'code') === 'string';
}

async function erreurDepuis(reponse: Response): Promise<ErreurApi> {
  try {
    const corps: unknown = await reponse.json();
    const detail = corps !== null && typeof corps === 'object' ? champ(corps, 'detail') : undefined;
    if (estDetailErreur(detail)) {
      return new ErreurApi(reponse.status, detail.code, detail.message, detail.remediation);
    }
  } catch (cause) {
    journal.erreur(`réponse ${reponse.status} illisible sur ${reponse.url}`, cause);
  }
  return new ErreurApi(reponse.status, 'reponse_inattendue', `Le backend a répondu ${reponse.status}.`, '');
}

async function appeler<T>(chemin: string, init: RequestInit): Promise<T> {
  let reponse: Response;
  try {
    reponse = await fetch(`${RACINE_API}${chemin}`, init);
  } catch (cause) {
    journal.erreur(`appel réseau impossible sur ${chemin}`, cause);
    throw new ErreurApi(0, 'reseau_indisponible', 'Le backend est injoignable.', 'Vérifier que le service tourne.');
  }
  if (!reponse.ok) {
    throw await erreurDepuis(reponse);
  }
  // Cast de frontière réseau : la forme est garantie par les modèles pydantic du backend, et
  // `api/types.ts` en est le miroir. Le vérifier champ par champ ici dupliquerait ce contrat.
  return (await reponse.json()) as T;
}

export function obtenir<T>(chemin: string, signal?: AbortSignal): Promise<T> {
  return appeler<T>(chemin, { method: 'GET', signal });
}

export function poster<T>(chemin: string, corps?: unknown, signal?: AbortSignal): Promise<T> {
  return appeler<T>(chemin, {
    method: 'POST',
    headers: corps === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: corps === undefined ? undefined : JSON.stringify(corps),
    signal,
  });
}

export function supprimer<T>(chemin: string, signal?: AbortSignal): Promise<T> {
  return appeler<T>(chemin, { method: 'DELETE', signal });
}

/** Message affichable d'une cause quelconque — les hooks n'ont pas à connaître `ErreurApi`. */
export function messageErreur(cause: unknown): string {
  if (cause instanceof ErreurApi) {
    return cause.remediation ? `${cause.message} — ${cause.remediation}` : cause.message;
  }
  if (cause instanceof Error) {
    return cause.message;
  }
  return 'Erreur inconnue.';
}
