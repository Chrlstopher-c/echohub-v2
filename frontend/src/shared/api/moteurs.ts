/*
 * Client du domaine `engines` — santé des moteurs et installation de vLLM.
 *
 * L'installation est un flux SSE sur un GET : `EventSource` ne sait faire que ça, et le backend a
 * assumé ce choix côté serveur. Fermer le flux (annuler le signal) annule réellement
 * l'installation : le générateur du backend est clos, son `finally` coupe le sous-processus et
 * supprime le venv partiel.
 */

import { fluxJson } from './sse';
import { requeteJson } from './transport';
import type { EtatMoteurs, EvenementInstallation, SanteMoteur, VersionVllm } from './types-moteurs';

/** Sonder chaque venv vLLM lance un interpréteur par version : c'est lent, jamais instantané. */
const DELAI_SONDE_MS = 120_000;

export interface OptionsEtatMoteurs {
  readonly forcerLlamacpp?: boolean;
  readonly verifierVllm?: boolean;
  readonly signal?: AbortSignal;
}

export function lireEtatMoteurs(options: OptionsEtatMoteurs = {}): Promise<EtatMoteurs> {
  return requeteJson<EtatMoteurs>('/engines/etat', {
    parametres: { forcer_llamacpp: options.forcerLlamacpp, verifier_vllm: options.verifierVllm },
    delaiMs: DELAI_SONDE_MS,
    signal: options.signal,
  });
}

export function lireSanteLlamaCpp(forcer = false, signal?: AbortSignal): Promise<SanteMoteur> {
  return requeteJson<SanteMoteur>('/engines/llamacpp/sante', {
    parametres: { forcer },
    delaiMs: DELAI_SONDE_MS,
    signal,
  });
}

export function listerVersionsVllm(verifier = false, signal?: AbortSignal): Promise<readonly VersionVllm[]> {
  return requeteJson<readonly VersionVllm[]>('/engines/vllm/versions', {
    parametres: { verifier },
    delaiMs: DELAI_SONDE_MS,
    signal,
  });
}

function cheminVersion(version: string): string {
  return `/engines/vllm/versions/${encodeURIComponent(version)}`;
}

/**
 * Flux d'installation. Chaque événement porte une progression d'ÉTAPES franchies : rien n'avance
 * tant que rien ne s'est terminé, contrairement à la barre 0 → 88 % en 6 s de la v1.
 */
export function fluxInstallationVllm(
  version: string,
  options: { readonly remplacer?: boolean; readonly signal?: AbortSignal } = {},
): AsyncGenerator<EvenementInstallation> {
  return fluxJson<EvenementInstallation>(`${cheminVersion(version)}/installation`, {
    methode: 'GET',
    parametres: { remplacer: options.remplacer },
    signal: options.signal,
  });
}

export function annulerInstallationVllm(version: string): Promise<{ readonly annulee: boolean }> {
  return requeteJson(`${cheminVersion(version)}/installation`, { methode: 'DELETE' });
}

export function supprimerVersionVllm(version: string): Promise<{ readonly version: string; readonly etat: string }> {
  return requeteJson(cheminVersion(version), { methode: 'DELETE', delaiMs: DELAI_SONDE_MS });
}
