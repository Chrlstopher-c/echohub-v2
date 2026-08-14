/*
 * Transport HTTP — un seul endroit construit une URL, pose un délai et traduit un échec.
 *
 * Les écrans n'appellent jamais `fetch` : ils passent par les clients de domaine, qui passent
 * par ici. C'est ce qui rend la gestion d'erreur réellement homogène plutôt que déclarée telle.
 */

import { ErreurApi, erreurReseau, normaliserErreur, CODE_ILLISIBLE } from './erreurs';

/**
 * Racine de l'API. `/api` en relatif par défaut : le proxy Vite en développement et nginx en
 * production servent la même URL, donc le code ne connaît aucun port.
 */
export const BASE_API: string = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '') || '/api';

/** Délai par défaut. Les routes qui mesurent le matériel ou compilent le relèvent explicitement. */
export const DELAI_DEFAUT_MS = 30_000;

export type MethodeHttp = 'GET' | 'POST' | 'PATCH' | 'DELETE';

/**
 * Un tableau produit un paramètre RÉPÉTÉ (`formats=gguf&formats=awq`) : c'est ce qu'attend un
 * `Query(list[...])` de FastAPI, et cela évite d'inventer une convention de séparateur que les
 * deux côtés devraient ensuite s'accorder à respecter.
 */
export type ValeurParametre = string | number | boolean | readonly string[] | undefined;

export interface OptionsRequete {
  readonly methode?: MethodeHttp;
  readonly corps?: unknown;
  readonly parametres?: Readonly<Record<string, ValeurParametre>>;
  readonly signal?: AbortSignal;
  /** Délai avant abandon. `0` désactive le délai — réservé aux flux, jamais à une requête simple. */
  readonly delaiMs?: number;
}

// Garde de type explicite : `Array.isArray` ne restreint pas correctement un `readonly T[]`.
function estListe(valeur: ValeurParametre): valeur is readonly string[] {
  return Array.isArray(valeur);
}

/** Construit l'URL complète. Les paramètres `undefined` sont omis, jamais sérialisés en "undefined". */
export function construireUrl(chemin: string, parametres?: Readonly<Record<string, ValeurParametre>>): string {
  const base = `${BASE_API}${chemin}`;
  if (parametres === undefined) return base;
  const requete = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(parametres)) {
    if (valeur === undefined) continue;
    if (estListe(valeur)) {
      for (const element of valeur) requete.append(cle, element);
    } else {
      requete.set(cle, String(valeur));
    }
  }
  const suffixe = requete.toString();
  return suffixe.length > 0 ? `${base}?${suffixe}` : base;
}

interface Attelage {
  readonly signal: AbortSignal;
  readonly liberer: () => void;
}

/**
 * Combine le signal de l'appelant et un délai en un seul signal, et rend de quoi tout libérer.
 * Écrit à la main plutôt qu'avec `AbortSignal.any` : cette API n'est pas disponible partout et un
 * `setTimeout` non annulé maintiendrait la page éveillée après chaque requête.
 */
function attelerSignaux(signalAppelant: AbortSignal | undefined, delaiMs: number): Attelage {
  const controleur = new AbortController();
  const expirer = (): void => controleur.abort(new DOMException('Délai dépassé', 'AbortError'));
  const chronometre = delaiMs > 0 ? window.setTimeout(expirer, delaiMs) : 0;
  const propager = (): void => controleur.abort(signalAppelant?.reason);
  if (signalAppelant !== undefined) {
    if (signalAppelant.aborted) propager();
    else signalAppelant.addEventListener('abort', propager, { once: true });
  }
  const liberer = (): void => {
    if (chronometre !== 0) window.clearTimeout(chronometre);
    signalAppelant?.removeEventListener('abort', propager);
  };
  return { signal: controleur.signal, liberer };
}

function entetes(corps: unknown): HeadersInit {
  const communs: Record<string, string> = { Accept: 'application/json' };
  if (corps !== undefined) communs['Content-Type'] = 'application/json';
  return communs;
}

/** Exécute la requête. Tout échec de transport devient une `ErreurApi` de statut 0. */
export async function executer(chemin: string, options: OptionsRequete = {}): Promise<Response> {
  const { methode = 'GET', corps, parametres, signal, delaiMs = DELAI_DEFAUT_MS } = options;
  const attelage = attelerSignaux(signal, delaiMs);
  try {
    return await fetch(construireUrl(chemin, parametres), {
      method: methode,
      headers: entetes(corps),
      body: corps === undefined ? null : JSON.stringify(corps),
      signal: attelage.signal,
    });
  } catch (cause) {
    throw erreurReseau(cause);
  } finally {
    attelage.liberer();
  }
}

/** Lit le corps sans jamais lever : une réponse d'erreur non-JSON reste exploitable. */
async function corpsSouple(reponse: Response): Promise<unknown> {
  try {
    const brut = await reponse.text();
    return brut.length === 0 ? undefined : (JSON.parse(brut) as unknown);
  } catch {
    return undefined;
  }
}

/**
 * Requête attendant une réponse JSON typée.
 *
 * Le type de retour est une promesse faite par l'appelant, pas une vérification : les types de
 * `types-*.ts` sont le miroir des modèles pydantic du backend, et c'est ce miroir qui doit rester
 * exact. Une divergence se voit à l'affichage, pas ici.
 */
export async function requeteJson<T>(chemin: string, options: OptionsRequete = {}): Promise<T> {
  const reponse = await executer(chemin, options);
  const corps = await corpsSouple(reponse);
  if (!reponse.ok) {
    throw new ErreurApi(reponse.status, normaliserErreur(corps, reponse.status));
  }
  if (corps === undefined) {
    throw new ErreurApi(reponse.status, {
      code: CODE_ILLISIBLE,
      message: `Réponse vide ou illisible sur ${chemin}.`,
      remediation: "Vérifier la version du backend : le contrat de cette route a changé.",
      details: { chemin },
    });
  }
  return corps as T;
}
