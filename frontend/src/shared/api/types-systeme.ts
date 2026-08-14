/*
 * Miroir TypeScript de `backend/system/modeles.py`.
 *
 * Les noms de champs restent en snake_case : ce sont les clés du JSON produit par pydantic. Les
 * renommer imposerait une couche de conversion, donc une seconde définition de la même donnée —
 * exactement la duplication que la v2 cherche à supprimer.
 *
 * Les champs marqués « dérivé » sont des `computed_field` pydantic : ils arrivent calculés par le
 * backend. L'interface les affiche, elle ne les recalcule jamais.
 */

export type Plateforme = 'wsl2' | 'linux_natif' | 'windows' | 'macos' | 'inconnue';

export type SourceMesureGpu = 'nvml' | 'nvidia_smi' | 'aucune';

/** La syntaxe d'exposition du GPU à Docker est INVERSÉE entre WSL2 et Linux natif. */
export type SyntaxeGpuDocker = 'deploy_reservations' | 'cdi';

export interface Gpu {
  readonly index: number;
  readonly nom: string;
  readonly compute_majeur: number | null;
  readonly compute_mineur: number | null;
  readonly vram_totale_octets: number;
  readonly vram_libre_octets: number;
  readonly vram_utilisee_octets: number;
  readonly utilisation_pct: number | null;
  readonly temperature_c: number | null;
  /** Dérivé — `sm_86`, `sm_120`. `null` quand la capacité de calcul n'a pas pu être lue. */
  readonly architecture_sm: string | null;
  /** Dérivé — conditionne l'avertissement sur le plancher de pilote 570. */
  readonly est_blackwell: boolean;
}

export interface PiloteNvidia {
  readonly version: string;
  /** Dérivé — `null` si la version est illisible ; on ne présume pas d'un pilote inconnu. */
  readonly version_majeure: number | null;
  /** Dérivé — faux aussi quand la version est illisible. */
  readonly supporte_blackwell: boolean;
}

export interface Memoire {
  readonly totale_octets: number;
  /** Ce qu'un processus peut réellement prendre, pas la mémoire « libre ». */
  readonly disponible_octets: number;
  /** Dérivé. */
  readonly utilisee_octets: number;
  /** Dérivé. */
  readonly pourcentage_utilise: number;
}

/** Ce que la plateforme INTERDIT ou IMPOSE — pas seulement son nom. */
export interface ContraintesPlateforme {
  readonly plateforme: Plateforme;
  /** Faux sous WSL2 : la mémoire unifiée y fige la VRAM à 2 Go (mesuré). */
  readonly memoire_unifiee_cuda: boolean;
  readonly variables_env_imposees: Readonly<Record<string, string>>;
  readonly ram_plafonnee_par_hote: boolean;
  readonly pin_memory_disponible: boolean;
  readonly syntaxe_gpu_docker: SyntaxeGpuDocker;
  readonly justifications: Readonly<Record<string, string>>;
}

/**
 * Instantané daté. Un profil relu plus tard décrit la machine telle qu'elle ÉTAIT : toujours en
 * redemander un avant de décider d'un chargement.
 */
export interface ProfilMachine {
  readonly mesure_le: string;
  readonly plateforme: Plateforme;
  readonly version_noyau: string;
  readonly contraintes: ContraintesPlateforme;
  readonly source_gpu: SourceMesureGpu;
  readonly pilote: PiloteNvidia | null;
  readonly gpus: readonly Gpu[];
  readonly memoire: Memoire | null;
  readonly avertissements: readonly string[];
  /** Dérivé. */
  readonly a_gpu: boolean;
  /** Dérivé — le GPU le mieux doté ; le seul que le planificateur considère. */
  readonly gpu_principal: Gpu | null;
  /** Dérivé — `0` sans GPU. */
  readonly vram_libre_octets: number;
  /** Dérivé. */
  readonly vram_totale_octets: number;
  /** Dérivé — distingue « rien de libre » de « on n'a pas pu mesurer ». */
  readonly memoire_mesuree: boolean;
  /** Dérivé — `0` quand la mesure a échoué : ne jamais planifier d'offload à l'aveugle. */
  readonly ram_disponible_octets: number;
}
