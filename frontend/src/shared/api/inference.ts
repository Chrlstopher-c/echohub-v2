/*
 * Client du domaine `inference` — planifier, dégrader, charger, observer, générer, décharger.
 *
 * Deux règles portées par ce fichier, et pas seulement par le backend :
 *
 * 1. `charger` transmet le plan DÉJÀ affiché à l'utilisateur. Replanifier au moment du chargement
 *    produirait un autre plan (la VRAM libre a pu changer) : l'utilisateur obtiendrait autre chose
 *    que ce qu'il a validé.
 * 2. après un échec, on appelle `degrader` — jamais on ne relance le même plan en montant un
 *    paramètre. C'était l'escalade de la v1 : contexte 55k → 131k après échec.
 */

import { fluxJson } from './sse';
import { requeteJson } from './transport';
import type { DemandeDeChargement, PlanDeChargement, ReponsePlan } from './types-plan';
import type {
  CauseEchecMoteur,
  EvenementInference,
  MessageMoteur,
  OptionsGenerationMoteur,
  SanteInference,
  SessionChargement,
  StatutInference,
} from './types-inference';

/** Un chargement peut compiler des kernels et lire plusieurs gigaoctets : le démarrage est lent. */
const DELAI_CHARGEMENT_MS = 120_000;

/** Marge au-delà du délai demandé à `/etat/attendre`, pour que ce soit le backend qui tranche. */
const MARGE_ATTENTE_MS = 5_000;

export function planifierChargement(demande: DemandeDeChargement, signal?: AbortSignal): Promise<ReponsePlan> {
  return requeteJson<ReponsePlan>('/inference/planifier', { methode: 'POST', corps: { demande }, signal });
}

export interface DemandeDegradation {
  readonly demande: DemandeDeChargement;
  readonly plan_echoue: PlanDeChargement;
  /** Omise, la cause est reprise de l'échec observé par le superviseur. */
  readonly cause?: CauseEchecMoteur | null;
}

export function degraderPlan(requete: DemandeDegradation, signal?: AbortSignal): Promise<ReponsePlan> {
  return requeteJson<ReponsePlan>('/inference/degrader', { methode: 'POST', corps: requete, signal });
}

/** Soit un plan déjà validé par l'utilisateur, soit une demande — jamais les deux, jamais aucun. */
export type RequeteChargement =
  | { readonly chemin_modele: string; readonly plan: PlanDeChargement }
  | { readonly chemin_modele: string; readonly demande: DemandeDeChargement };

/** Rend la main dès le démarrage (202) : l'avancement se lit sur `lireEtatInference`. */
export function chargerModele(requete: RequeteChargement, signal?: AbortSignal): Promise<StatutInference> {
  return requeteJson<StatutInference>('/inference/charger', {
    methode: 'POST',
    corps: requete,
    delaiMs: DELAI_CHARGEMENT_MS,
    signal,
  });
}

export function lireEtatInference(signal?: AbortSignal): Promise<StatutInference> {
  return requeteJson<StatutInference>('/inference/etat', { signal });
}

/** Attente longue côté serveur, pour les écrans qui ne sondent pas en boucle. */
export function attendreEtatInference(delaiSecondes = 60, signal?: AbortSignal): Promise<StatutInference> {
  return requeteJson<StatutInference>('/inference/etat/attendre', {
    parametres: { delai_s: delaiSecondes },
    delaiMs: delaiSecondes * 1000 + MARGE_ATTENTE_MS,
    signal,
  });
}

export function lireJournalChargements(limite = 10, signal?: AbortSignal): Promise<readonly SessionChargement[]> {
  return requeteJson<readonly SessionChargement[]>('/inference/journal', { parametres: { limite }, signal });
}

/** Sonde le moteur maintenant : un moteur mort n'apparaît pas dans l'état mémorisé. */
export function sonderSanteInference(signal?: AbortSignal): Promise<SanteInference> {
  return requeteJson<SanteInference>('/inference/sante', { signal });
}

/** Éjecte le modèle courant et vérifie que la VRAM est réellement rendue. */
export function dechargerModele(signal?: AbortSignal): Promise<StatutInference> {
  return requeteJson<StatutInference>('/inference/decharger', {
    methode: 'POST',
    delaiMs: DELAI_CHARGEMENT_MS,
    signal,
  });
}

export interface DemandeGenerationDirecte {
  readonly messages: readonly MessageMoteur[];
  readonly options?: OptionsGenerationMoteur;
}

/**
 * Génération sans conversation persistée — bancs d'essai et diagnostic. Le chat passe par
 * `chat.ts`, qui écrit l'historique. Le flux se termine par la sentinelle `[DONE]`, consommée
 * par `fluxJson`.
 */
export function genererDirect(
  requete: DemandeGenerationDirecte,
  signal?: AbortSignal,
): AsyncGenerator<EvenementInference> {
  return fluxJson<EvenementInference>('/inference/generer', { methode: 'POST', corps: requete, signal });
}
