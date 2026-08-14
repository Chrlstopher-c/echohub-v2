/*
 * Appels du domaine `engines` : état de santé, versions vLLM, suppression, annulation.
 *
 * L'installation ne passe pas par ici : c'est un flux SSE, piloté par `moteurs/useInstallationVllm`.
 */

import { obtenir, supprimer } from './client';
import { ROUTES } from './routes';
import type { EtatMoteurs, SanteMoteur, VersionVllm } from './types';

export interface OptionsEtat {
  /** Relance la sonde llama.cpp au lieu de relire la dernière mesure. */
  forcerLlamacpp?: boolean;
  /** Sonde chaque venv vLLM : plusieurs secondes par venv, à ne pas faire à chaque affichage. */
  verifierVllm?: boolean;
}

export function lireEtatMoteurs(options: OptionsEtat = {}, signal?: AbortSignal): Promise<EtatMoteurs> {
  return obtenir<EtatMoteurs>(ROUTES.etatMoteurs(options), signal);
}

export function sonderLlamacpp(signal?: AbortSignal): Promise<SanteMoteur> {
  return obtenir<SanteMoteur>(ROUTES.santeLlamacpp(true), signal);
}

export function listerVersionsVllm(verifier: boolean, signal?: AbortSignal): Promise<VersionVllm[]> {
  return obtenir<VersionVllm[]>(ROUTES.versionsVllm(verifier), signal);
}

export function annulerInstallationVllm(version: string): Promise<{ annulee: boolean }> {
  return supprimer<{ annulee: boolean }>(ROUTES.annulationInstallationVllm(version));
}

export function supprimerVersionVllm(version: string): Promise<{ version: string; etat: string }> {
  return supprimer<{ version: string; etat: string }>(ROUTES.versionVllm(version));
}
