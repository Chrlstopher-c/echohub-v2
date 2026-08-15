/*
 * Miroir TypeScript de l'interface publique de `backend/models/`.
 *
 * Distinction structurante, reprise telle quelle du backend : ce que le Hub ANNONCE
 * (`MetadonneesAnnoncees`) n'a pas valeur de mesure. Seul ce qui est lu dans le fichier après
 * téléchargement (`MetadonneesGGUF`) en a. La v1 confondait les deux et calculait un nombre de
 * paramètres, un contexte et une VRAM à partir d'un nom de dépôt — les trois étaient faux.
 */

/*
 * `FormatModele` est défini une seule fois, dans `types-plan.ts` : côté backend, `storage.py` et
 * `planner/entrees.py` déclarent la même énumération. La dupliquer ici en ferait deux définitions
 * capables de diverger, et rendrait l'export ambigu depuis `index.ts`.
 */
export type { FormatModele } from './types-plan';
import type { FormatModele } from './types-plan';

export type FormatRecherche = 'gguf' | 'awq' | 'gptq' | 'safetensors';

export type TriRecherche = 'downloads' | 'likes' | 'created_at' | 'last_modified' | 'trending_score';

export type Ordre = 'desc' | 'asc';

/** Entrée du registre local — ce qui est réellement présent sur le disque. */
export interface ModeleEnregistre {
  readonly id: string;
  readonly depot: string;
  readonly fichier: string | null;
  readonly chemin: string;
  readonly format: FormatModele;
  readonly taille_octets: number;
  readonly quantification: string | null;
  readonly architecture: string | null;
  readonly nb_couches: number | null;
  readonly contexte_max: number | null;
  readonly ajoute_le: string;
}

export interface ResumeSynchronisation {
  readonly entrees_supprimees: readonly string[];
  readonly entrees_ajoutees: readonly string[];
  readonly dossiers_ignores: readonly string[];
}

/** `etiquette` vient du nom de fichier : c'est une intention affichée, pas un fait mesuré. */
export interface FichierDepot {
  readonly nom: string;
  readonly taille_octets: number | null;
  readonly etiquette: string | null;
}

/** À présenter systématiquement comme « annoncé » : sert à choisir un dépôt, pas à dimensionner. */
export interface MetadonneesAnnoncees {
  readonly architecture: string | null;
  readonly contexte: number | null;
  readonly nb_parametres: number | null;
}

export interface ResultatRecherche {
  readonly depot: string;
  readonly nom: string;
  readonly auteur: string | null;
  readonly telechargements: number | null;
  readonly mentions: number | null;
  readonly tendance: number | null;
  readonly modifie_le: string | null;
  readonly gated: boolean;
  readonly tache: string | null;
  readonly etiquettes: readonly string[];
  readonly formats: readonly FormatModele[];
  readonly fichiers_gguf: readonly FichierDepot[];
  readonly taille_totale_octets: number | null;
  readonly annonce: MetadonneesAnnoncees;
  readonly deja_telecharge: boolean;
}

export interface PageRecherche {
  readonly resultats: readonly ResultatRecherche[];
  readonly page: number;
  readonly taille_page: number;
  readonly fin_atteinte: boolean;
}

export type EtatTelechargement =
  | 'en_attente'
  | 'en_cours'
  | 'termine'
  | 'annule'
  /** Processus mort sans verdict : les octets écrits restent, relancer reprend où ça s'est arrêté. */
  | 'interrompu'
  | 'erreur';

export interface Telechargement {
  readonly identifiant: string;
  readonly depot: string;
  readonly fichier: string | null;
  readonly revision: string;
  readonly chemin: string;
  readonly etat: EtatTelechargement;
  readonly octets_recus: number;
  /** `null` tant que le Hub n'a pas annoncé les tailles : pas de pourcentage plutôt qu'un faux. */
  readonly octets_totaux: number | null;
  readonly erreur: string | null;
  readonly remediation: string | null;
  readonly demarre_le: string;
  readonly maj_le: string;
  readonly termine_le: string | null;
  /** Dérivé — `null` si le total est inconnu. */
  readonly progression: number | null;
}

export type NiveauIncoherence = 'avertissement' | 'bloquant';

export interface Incoherence {
  readonly code: string;
  readonly niveau: NiveauIncoherence;
  readonly message: string;
  readonly remediation: string;
  readonly details: Readonly<Record<string, unknown>>;
}

/** Confrontation du déclaré au présent. `bloquant` = le chargement échouera, inutile d'essayer. */
export interface RapportCoherence {
  readonly chemin: string;
  readonly format: FormatModele | null;
  readonly incoherences: readonly Incoherence[];
}

export interface ParametresAttention {
  readonly nb_tetes: number | null;
  readonly nb_tetes_kv: number | null;
  readonly nb_tetes_kv_par_bloc: readonly number[] | null;
  readonly dimension_cle: number | null;
  readonly dimension_valeur: number | null;
  readonly dimension_rope: number | null;
  readonly base_rope: number | null;
}

/** Poids RÉEL de chaque bloc, descripteur par descripteur — remplace le « 150 Mo/couche » de la v1. */
export interface MesuresTenseurs {
  readonly octets_par_bloc: readonly number[];
  readonly octets_hors_blocs: number;
  readonly octets_totaux: number;
  readonly blocs_observes: number;
  readonly types_ggml_inconnus: readonly number[];
}

/** D'où vient `block_count` : la clé GGUF, ou le décompte des tenseurs réellement présents. */
export type SourceBlockCount = 'cle_gguf' | 'index_des_tenseurs';

export interface MetadonneesGGUF {
  readonly chemin: string;
  readonly taille_fichier_octets: number;
  readonly version_gguf: number;
  readonly architecture: string;
  readonly nom: string | null;
  readonly block_count: number;
  readonly source_block_count: SourceBlockCount;
  readonly contexte_natif: number | null;
  readonly longueur_embedding: number | null;
  readonly longueur_feed_forward: number | null;
  readonly nb_experts: number | null;
  readonly nb_experts_actifs: number | null;
  readonly attention: ParametresAttention;
  readonly quantification_declaree: string | null;
  readonly quantification_mesuree: string | null;
  readonly nb_tenseurs: number;
  readonly taille_vocabulaire: number | null;
  readonly mesures: MesuresTenseurs | null;
  /**
   * Dérivés, calculés par le backend et sérialisés — ne jamais les recalculer ici.
   *
   * `largeur_ffn_active` est la largeur FFN réellement vive pour un token : `longueur_feed_forward`
   * sur un modèle dense, et sur un MoE la largeur d'un expert multipliée par le nombre d'experts
   * routés, plus la branche partagée. C'est CETTE grandeur qui dimensionne un budget mémoire ;
   * `longueur_feed_forward` vaut `null` sur les architectures MoE, qui ne déclarent pas cette clé.
   */
  readonly est_moe: boolean;
  readonly largeur_ffn_active: number | null;
}
