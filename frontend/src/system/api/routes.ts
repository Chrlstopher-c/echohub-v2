/*
 * Tous les chemins HTTP consommés par le domaine `system`, réunis ici.
 *
 * Un seul fichier à corriger si le backend déplace un point d'entrée. Les chemins des domaines
 * `system` et `engines` sont repris de leurs routeurs FastAPI (`backend/system/api.py`,
 * `backend/engines/api.py`), qui portent leur préfixe et sont montés sous `/api`.
 */

export const ROUTES = {
  /** Profil matériel mesuré à l'instant de l'appel — jamais mémorisé côté backend. */
  profil: '/system/profil',

  /** État de santé des deux moteurs. `verifier_vllm` sonde chaque venv : c'est lent. */
  etatMoteurs: (options: { forcerLlamacpp?: boolean; verifierVllm?: boolean } = {}): string => {
    const parametres = new URLSearchParams({
      forcer_llamacpp: String(options.forcerLlamacpp ?? false),
      verifier_vllm: String(options.verifierVllm ?? false),
    });
    return `/engines/etat?${parametres.toString()}`;
  },

  santeLlamacpp: (forcer: boolean): string => `/engines/llamacpp/sante?forcer=${String(forcer)}`,

  versionsVllm: (verifier: boolean): string => `/engines/vllm/versions?verifier=${String(verifier)}`,

  /** Flux SSE d'installation. GET imposé par `EventSource`, qui ne sait pas émettre de POST. */
  installationVllm: (version: string, remplacer: boolean): string =>
    `/engines/vllm/versions/${encodeURIComponent(version)}/installation?remplacer=${String(remplacer)}`,

  annulationInstallationVllm: (version: string): string =>
    `/engines/vllm/versions/${encodeURIComponent(version)}/installation`,

  versionVllm: (version: string): string => `/engines/vllm/versions/${encodeURIComponent(version)}`,
} as const;
