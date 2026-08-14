/*
 * Miroir TypeScript de `backend/engines/modeles.py`.
 *
 * `installe`, `fonctionnel`, `couvre_le_parc` et `utilisable` sont dérivés de `statut` par le
 * backend : ne jamais les recalculer côté interface, c'est la contradiction qu'avait la v1 entre
 * « installé » et « opérationnel ».
 */

export type NomMoteur = 'llamacpp' | 'vllm';

export type NiveauEvenement = 'info' | 'avertissement' | 'erreur' | 'succes';

export type StatutMoteur =
  /** rien d'installé */
  | 'absent'
  /** présent sur le disque mais jamais validé : installation interrompue */
  | 'incomplet'
  /** installé, mais la sonde échoue ou révèle un binaire inutilisable */
  | 'defaillant'
  /** sonde passée : importable et capable de toucher le GPU */
  | 'fonctionnel';

export type EtapeInstallation =
  | 'preparation'
  | 'creation_venv'
  | 'mise_a_jour_pip'
  | 'installation_vllm'
  | 'alignement_transformers'
  | 'validation'
  | 'finalisation'
  | 'annulation'
  | 'echec';

export interface SanteMoteur {
  readonly moteur: NomMoteur;
  readonly statut: StatutMoteur;
  readonly version: string | null;
  /** Architectures CUDA réellement embarquées par le binaire — `sm_86`, `sm_120`. */
  readonly architectures_gpu: readonly string[];
  readonly diagnostic: string;
  readonly remediation: string;
  /** Constats bruts destinés à l'affichage (FORCE_CUBLAS, version de torch, chemin du venv…). */
  readonly details: Readonly<Record<string, string>>;
  readonly mesure_le: string;
  /** Dérivé. */
  readonly installe: boolean;
  /** Dérivé — vérifié par une sonde réelle, jamais déduit de la seule présence. */
  readonly fonctionnel: boolean;
  /** Dérivé — le binaire couvre-t-il sm_86 ET sm_120 ? */
  readonly couvre_le_parc: boolean;
}

export interface VersionVllm {
  readonly version: string;
  readonly chemin: string;
  readonly python: string;
  readonly statut: StatutMoteur;
  readonly version_installee: string | null;
  readonly version_transformers: string | null;
  readonly version_torch: string | null;
  readonly architectures_gpu: readonly string[];
  readonly taille_octets: number | null;
  readonly installee_le: string | null;
  readonly diagnostic: string;
  /** Dérivé — seul un venv validé peut servir à charger un modèle. */
  readonly utilisable: boolean;
}

/**
 * Événement du flux d'installation. `progression` est le rapport d'étapes RÉELLEMENT franchies —
 * jamais une estimation de durée, la barre ne bouge que quand quelque chose s'est terminé.
 */
export interface EvenementInstallation {
  readonly version: string;
  readonly etape: EtapeInstallation;
  readonly message: string;
  readonly niveau: NiveauEvenement;
  readonly progression: number;
  readonly termine: boolean;
  readonly succes: boolean | null;
  readonly horodatage: string;
}

export interface EtatMoteurs {
  readonly llamacpp: SanteMoteur;
  readonly vllm: SanteMoteur;
  readonly versions_vllm: readonly VersionVllm[];
  readonly mesure_le: string;
}
