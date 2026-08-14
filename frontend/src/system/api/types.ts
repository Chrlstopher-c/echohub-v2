/*
 * Miroir TypeScript des modèles pydantic exposés par les domaines backend `system` et `engines`.
 *
 * Les noms de champs sont ceux du backend, sans traduction ni renommage : un écart de nom entre les
 * deux côtés est une source de bug silencieux que rien ne rattrape au build.
 *
 * Les champs marqués « dérivé » sont des `computed_field` pydantic. Ils arrivent calculés dans la
 * réponse : l'interface les affiche, elle ne les recalcule jamais.
 */

export type Plateforme = 'wsl2' | 'linux_natif' | 'windows' | 'macos' | 'inconnue';

export type SourceMesureGpu = 'nvml' | 'nvidia_smi' | 'aucune';

export type SyntaxeGpuDocker = 'deploy_reservations' | 'cdi';

export interface Gpu {
  index: number;
  nom: string;
  compute_majeur: number | null;
  compute_mineur: number | null;
  vram_totale_octets: number;
  vram_libre_octets: number;
  vram_utilisee_octets: number;
  utilisation_pct: number | null;
  temperature_c: number | null;
  /** dérivé — `sm_120` sur Blackwell, `null` si la capacité de calcul n'a pas été lue. */
  architecture_sm: string | null;
  /** dérivé — conditionne le plancher de pilote à 570. */
  est_blackwell: boolean;
}

export interface PiloteNvidia {
  version: string;
  /** dérivé */
  version_majeure: number | null;
  /** dérivé — `false` aussi quand la version est illisible : on ne présume pas d'un pilote inconnu. */
  supporte_blackwell: boolean;
}

export interface Memoire {
  totale_octets: number;
  disponible_octets: number;
  /** dérivé */
  utilisee_octets: number;
  /** dérivé */
  pourcentage_utilise: number;
}

/**
 * Ce que la plateforme INTERDIT ou IMPOSE. `justifications` est indexé par nom de champ : chaque
 * contrainte porte le texte de la mesure qui l'a établie, et c'est ce texte que l'écran affiche.
 */
export interface ContraintesPlateforme {
  plateforme: Plateforme;
  memoire_unifiee_cuda: boolean;
  variables_env_imposees: Record<string, string>;
  ram_plafonnee_par_hote: boolean;
  pin_memory_disponible: boolean;
  syntaxe_gpu_docker: SyntaxeGpuDocker;
  justifications: Record<string, string>;
}

export interface ProfilMachine {
  mesure_le: string;
  plateforme: Plateforme;
  version_noyau: string;
  contraintes: ContraintesPlateforme;
  source_gpu: SourceMesureGpu;
  pilote: PiloteNvidia | null;
  gpus: Gpu[];
  memoire: Memoire | null;
  avertissements: string[];
  /** dérivé */
  a_gpu: boolean;
  /** dérivé — le mieux doté en VRAM ; le GPU est traité comme une ressource exclusive. */
  gpu_principal: Gpu | null;
  /** dérivé */
  vram_libre_octets: number;
  /** dérivé */
  vram_totale_octets: number;
  /** dérivé — distingue « rien de libre » de « mesure impossible ». */
  memoire_mesuree: boolean;
  /** dérivé */
  ram_disponible_octets: number;
}

// --- domaine `engines` ------------------------------------------------------------------------

export type NomMoteur = 'llamacpp' | 'vllm';

export type StatutMoteur = 'absent' | 'incomplet' | 'defaillant' | 'fonctionnel';

export type NiveauEvenement = 'info' | 'avertissement' | 'erreur' | 'succes';

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
  moteur: NomMoteur;
  statut: StatutMoteur;
  version: string | null;
  architectures_gpu: string[];
  diagnostic: string;
  remediation: string;
  details: Record<string, string>;
  mesure_le: string;
  /** dérivé */
  installe: boolean;
  /** dérivé — vérifié par une sonde réelle, jamais déduit de la présence du binaire. */
  fonctionnel: boolean;
  /** dérivé — le binaire embarque-t-il sm_86 ET sm_120 ? */
  couvre_le_parc: boolean;
}

export interface VersionVllm {
  version: string;
  chemin: string;
  python: string;
  statut: StatutMoteur;
  version_installee: string | null;
  version_transformers: string | null;
  version_torch: string | null;
  architectures_gpu: string[];
  taille_octets: number | null;
  installee_le: string | null;
  diagnostic: string;
  /** dérivé */
  utilisable: boolean;
}

export interface EtatMoteurs {
  llamacpp: SanteMoteur;
  vllm: SanteMoteur;
  versions_vllm: VersionVllm[];
  mesure_le: string;
}

/** Un événement du flux d'installation. `progression` est une fraction d'étapes RÉELLEMENT franchies. */
export interface EvenementInstallation {
  version: string;
  etape: EtapeInstallation;
  message: string;
  niveau: NiveauEvenement;
  progression: number;
  termine: boolean;
  succes: boolean | null;
  horodatage: string;
}
