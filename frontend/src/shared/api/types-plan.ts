/*
 * Miroir TypeScript de `backend/inference/planner/` — entrées du planificateur et plan produit.
 *
 * C'est le contrat le plus important du projet : le plan est SEULE source de vérité. L'interface
 * affiche `justification` et `plafonnee`, elle ne dérive aucune de ces valeurs. Recalculer ici
 * « combien de couches tiennent » reproduirait le défaut central de la v1 — deux endroits qui
 * décident, et qui finissent par ne plus dire la même chose.
 */

export type Moteur = 'llama.cpp' | 'vllm';

export type FormatModele = 'gguf' | 'safetensors';

/** Compression croissante : F16 > Q8_0 > Q4_0. */
export type TypeCacheKV = 'f16' | 'q8_0' | 'q4_0';

/**
 * Plateformes que le planificateur accepte. Strictement plus étroit que `Plateforme` du domaine
 * `system` (qui connaît aussi `macos` et `inconnue`) : une machine hors de ces trois cas n'a pas
 * de plan, il faut le dire à l'utilisateur plutôt que de choisir une valeur au hasard.
 */
export type PlateformePlan = 'linux_natif' | 'wsl2' | 'windows';

/** Métadonnées LUES dans le modèle. Jamais déduites d'un nom de fichier. */
export interface MetadonneesModele {
  readonly identifiant: string;
  readonly format: FormatModele;
  readonly architecture: string;
  readonly taille_octets: number;
  /** `{arch}.block_count` — nombre RÉEL de couches (41 mesurées là où la v1 en estimait 80). */
  readonly nombre_couches: number;
  readonly dimension_embedding: number;
  readonly dimension_ffn: number;
  readonly nombre_tetes_attention: number;
  readonly nombre_tetes_kv: number;
  /** Absente sur certaines architectures ; Qwen3 en déclare une hors convention. */
  readonly dimension_tete?: number | null;
  readonly contexte_entrainement_max: number;
  readonly taille_vocabulaire: number;
  readonly quantification?: string | null;
  readonly est_moe?: boolean;
}

/** Modèle déjà résident : le GPU est exclusif, tout ce qui est listé ici devra être éjecté. */
export interface ModeleCharge {
  readonly identifiant: string;
  readonly moteur: Moteur;
  readonly vram_octets: number;
}

/** État matériel au moment du chargement — pas au démarrage du backend. */
export interface ProfilPlanification {
  readonly plateforme: PlateformePlan;
  readonly index_gpu?: number;
  readonly nom_gpu?: string;
  readonly vram_totale_octets: number;
  /** Inclut déjà la réserve du bureau Windows : ne rien re-soustraire, ce serait un double compte. */
  readonly vram_libre_octets: number;
  readonly ram_libre_octets: number;
  readonly moteurs_disponibles?: readonly Moteur[];
  readonly modeles_charges?: readonly ModeleCharge[];
  readonly capacite_calcul?: readonly [number, number] | null;
}

/** Ce que l'utilisateur demande. Rien n'est garanti : tout est plafonné par la machine. */
export interface PreferencesUtilisateur {
  readonly contexte?: number | null;
  readonly batch?: number | null;
  readonly couches_gpu?: number | null;
  readonly type_cache_kv?: TypeCacheKV;
  readonly moteur?: Moteur | null;
  readonly flash_attention?: boolean;
  /** Nuisible sous WSL2 (VRAM figée à 2 Go, mesuré) : la plateforme tranche, pas cette préférence. */
  readonly autoriser_memoire_unifiee?: boolean;
  readonly ratio_fragmentation?: number;
}

export interface DemandeDeChargement {
  readonly metadonnees: MetadonneesModele;
  readonly profil: ProfilPlanification;
  readonly preferences?: PreferencesUtilisateur;
}

/** Une valeur du plan et la phrase qui l'explique. */
export interface ValeurJustifiee<T> {
  readonly valeur: T;
  readonly justification: string;
  /** Vrai quand la machine a imposé la valeur : distingue le choix subi du choix demandé. */
  readonly plafonnee: boolean;
  readonly valeur_demandee: T | null;
}

/** Une ligne du budget mémoire : à quoi servent ces octets, et d'où sort le chiffre. */
export interface PosteMemoire {
  readonly libelle: string;
  readonly octets: number;
  readonly justification: string;
}

/**
 * Décomposition de la VRAM engagée. `vram_requise_octets` et `vram_restante_octets` ne sont PAS
 * sérialisés (ce sont des `@property`, pas des `computed_field`) : voir `derivations.ts`, qui en
 * donne le miroir exact — une somme, pas une décision.
 */
export interface BudgetMemoire {
  readonly vram_disponible_octets: number;
  readonly postes: readonly PosteMemoire[];
  readonly ram_requise_octets: number;
  readonly ram_disponible_octets: number;
}

export interface VariableEnvironnement {
  readonly nom: string;
  readonly valeur: string;
  readonly justification: string;
}

/** Variable délibérément NON posée — cas de référence : `GGML_CUDA_ENABLE_UNIFIED_MEMORY` sous WSL2. */
export interface VariableRefusee {
  readonly nom: string;
  readonly raison: string;
}

export interface EjectionRequise {
  readonly identifiant: string;
  readonly moteur: Moteur;
  readonly vram_liberee_octets: number;
  readonly raison: string;
}

/** Réponse complète à « comment charger ce modèle sur cette machine, maintenant ? ». */
export interface PlanDeChargement {
  readonly identifiant_modele: string;
  /** `0` = plan nominal. Chaque échec produit un plan de niveau supérieur, donc plus prudent. */
  readonly niveau_degradation: number;
  readonly moteur: ValeurJustifiee<Moteur>;
  readonly couches_gpu: ValeurJustifiee<number>;
  readonly couches_totales: number;
  readonly contexte: ValeurJustifiee<number>;
  readonly batch: ValeurJustifiee<number>;
  readonly type_cache_kv: ValeurJustifiee<TypeCacheKV>;
  readonly flash_attention: ValeurJustifiee<boolean>;
  /** vLLM seulement : ce moteur raisonne en fraction de VRAM préallouée, pas en couches. */
  readonly utilisation_memoire_gpu: ValeurJustifiee<number> | null;
  readonly variables_environnement: readonly VariableEnvironnement[];
  readonly variables_refusees: readonly VariableRefusee[];
  readonly ejections_requises: readonly EjectionRequise[];
  readonly budget: BudgetMemoire;
  readonly avertissements: readonly string[];
}

/** Le plan et ses justifications, prêts à l'affichage. */
export interface ReponsePlan {
  readonly plan: PlanDeChargement;
  readonly justifications: readonly string[];
  readonly avertissements: readonly string[];
}
