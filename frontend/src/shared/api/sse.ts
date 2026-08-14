/*
 * Lecture des flux SSE du backend (génération de tokens, installation d'un moteur).
 *
 * `EventSource` n'est pas utilisé : il ne sait émettre que des GET, alors que deux des trois flux
 * sont des POST porteurs d'un corps. Un `fetch` + `ReadableStream` couvre les deux cas et donne en
 * prime l'annulation par `AbortSignal`, dont dépend le bouton « Arrêter » du chat.
 *
 * Aucune boucle de ce module n'est libre : le nombre de lectures et le nombre d'événements sont
 * bornés. Un backend qui ne fermerait jamais son flux fige l'onglet, il ne doit pas pouvoir.
 */

import { ErreurApi, erreurReseau, normaliserErreur, CODE_FLUX_TROP_LONG, CODE_ILLISIBLE } from './erreurs';
import { construireUrl, type MethodeHttp, type ValeurParametre } from './transport';

/** Sentinelle de fin employée par `/api/inference/generer`. Ce n'est pas du JSON. */
export const SENTINELLE_FIN = '[DONE]';

/** Délai d'ouverture. Il ne borne QUE la connexion : un flux ouvert peut durer des heures. */
const DELAI_CONNEXION_MS = 20_000;

/** Plafond d'événements. Au-delà du plus long flux plausible (une génération de 262 144 tokens). */
const MAX_EVENEMENTS_DEFAUT = 400_000;

/** Plafond de lectures réseau : un morceau peut ne contenir aucune trame complète. */
const MAX_LECTURES = 2_000_000;

export interface OptionsFlux {
  readonly methode?: MethodeHttp;
  readonly corps?: unknown;
  readonly parametres?: Readonly<Record<string, ValeurParametre>>;
  readonly signal?: AbortSignal;
  readonly maxEvenements?: number;
  readonly delaiConnexionMs?: number;
}

interface Connexion {
  readonly reponse: Response;
  readonly fermer: () => void;
}

/** Ouvre le flux. Le délai n'arme que la phase de connexion, puis il est désamorcé. */
async function ouvrir(chemin: string, options: OptionsFlux): Promise<Connexion> {
  const controleur = new AbortController();
  const propager = (): void => controleur.abort(options.signal?.reason);
  options.signal?.addEventListener('abort', propager, { once: true });
  const fermer = (): void => {
    options.signal?.removeEventListener('abort', propager);
    controleur.abort();
  };
  const chronometre = window.setTimeout(
    () => controleur.abort(new DOMException('Délai de connexion dépassé', 'AbortError')),
    options.delaiConnexionMs ?? DELAI_CONNEXION_MS,
  );
  try {
    const reponse = await fetch(construireUrl(chemin, options.parametres), {
      method: options.methode ?? 'POST',
      headers: enteteFlux(options.corps),
      body: options.corps === undefined ? null : JSON.stringify(options.corps),
      signal: controleur.signal,
    });
    return { reponse, fermer };
  } catch (cause) {
    fermer();
    throw erreurReseau(cause);
  } finally {
    window.clearTimeout(chronometre);
  }
}

function enteteFlux(corps: unknown): HeadersInit {
  const communs: Record<string, string> = { Accept: 'text/event-stream' };
  if (corps !== undefined) communs['Content-Type'] = 'application/json';
  return communs;
}

/** Un refus arrive AVANT le flux (404 conversation inconnue, 409 aucun modèle prêt). */
async function refuser(reponse: Response): Promise<never> {
  let corps: unknown;
  try {
    corps = JSON.parse(await reponse.text()) as unknown;
  } catch {
    corps = undefined;
  }
  throw new ErreurApi(reponse.status, normaliserErreur(corps, reponse.status));
}

interface Decoupe {
  readonly trames: readonly string[];
  readonly reste: string;
}

function decouper(tampon: string): Decoupe {
  const morceaux = tampon.split('\n\n');
  // La dernière portion n'est pas terminée par un séparateur : elle attend le morceau suivant.
  const reste = morceaux.pop() ?? '';
  return { trames: morceaux, reste };
}

/** Extrait la charge utile d'une trame. Les lignes de commentaire (`:`) sont ignorées. */
function charge(trame: string): string | undefined {
  const lignes = trame.split('\n').filter((ligne) => ligne.startsWith('data:'));
  if (lignes.length === 0) return undefined;
  return lignes.map((ligne) => ligne.slice('data:'.length).replace(/^ /, '')).join('\n');
}

function tropLong(limite: number): ErreurApi {
  return new ErreurApi(0, {
    code: CODE_FLUX_TROP_LONG,
    message: `Le flux a dépassé ${limite} événements sans se terminer.`,
    remediation: "Le moteur ne clôt pas son flux : recharger le modèle depuis l'écran Système.",
    details: { limite },
  });
}

async function* lireTrames(flux: ReadableStream<Uint8Array>, maxEvenements: number): AsyncGenerator<string> {
  // Décodage manuel plutôt que `TextDecoderStream` : `{ stream: true }` recolle les caractères
  // multi-octets coupés entre deux morceaux, sans dépendre d'une API de flux inégalement typée.
  const lecteur = flux.getReader();
  const decodeur = new TextDecoder();
  let tampon = '';
  let emis = 0;
  try {
    for (let lecture = 0; lecture < MAX_LECTURES; lecture += 1) {
      const morceau = await lecteur.read();
      if (morceau.done) return;
      const decoupe = decouper(tampon + decodeur.decode(morceau.value, { stream: true }).replace(/\r\n/g, '\n'));
      tampon = decoupe.reste;
      for (const trame of decoupe.trames) {
        const utile = charge(trame);
        if (utile === undefined) continue;
        emis += 1;
        if (emis > maxEvenements) throw tropLong(maxEvenements);
        yield utile;
      }
    }
    throw tropLong(maxEvenements);
  } finally {
    await annuler(lecteur);
  }
}

async function annuler(lecteur: ReadableStreamDefaultReader<Uint8Array>): Promise<void> {
  try {
    await lecteur.cancel();
  } catch (cause) {
    // Attendu quand le flux s'est déjà refermé de lui-même ; tracé pour ne pas masquer le reste.
    console.debug('Fermeture du flux SSE déjà effective :', cause);
  }
}

/** Flux d'événements bruts (la charge de chaque `data:`), sentinelle comprise. */
export async function* fluxSse(chemin: string, options: OptionsFlux = {}): AsyncGenerator<string> {
  const connexion = await ouvrir(chemin, options);
  try {
    if (!connexion.reponse.ok) await refuser(connexion.reponse);
    const corps = connexion.reponse.body;
    if (corps === null) {
      throw new ErreurApi(connexion.reponse.status, {
        code: CODE_ILLISIBLE,
        message: `Le flux ${chemin} n'a pas de corps lisible.`,
        remediation: 'Vérifier que le proxy ne tamponne pas la réponse (`proxy_buffering off`).',
        details: { chemin },
      });
    }
    yield* lireTrames(corps, options.maxEvenements ?? MAX_EVENEMENTS_DEFAUT);
  } finally {
    connexion.fermer();
  }
}

/** Idem, mais chaque événement est décodé en JSON. La sentinelle `[DONE]` termine le flux. */
export async function* fluxJson<T>(chemin: string, options: OptionsFlux = {}): AsyncGenerator<T> {
  for await (const utile of fluxSse(chemin, options)) {
    if (utile === SENTINELLE_FIN) return;
    yield decoder<T>(utile, chemin);
  }
}

function decoder<T>(utile: string, chemin: string): T {
  try {
    return JSON.parse(utile) as T;
  } catch (cause) {
    throw new ErreurApi(0, {
      code: CODE_ILLISIBLE,
      message: `Événement illisible sur ${chemin}.`,
      remediation: "Le backend a émis autre chose que du JSON : c'est un défaut de contrat.",
      details: { extrait: utile.slice(0, 200), cause: String(cause) },
    });
  }
}
