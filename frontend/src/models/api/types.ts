/*
 * Miroir TypeScript des modèles pydantic du domaine backend `models`.
 *
 * Une distinction structure tout ce fichier, et c'est celle du domaine : ce que le Hub **annonce**
 * n'est pas ce que le fichier **contient**. `ResultatRecherche` et `MetadonneesAnnoncees` sont des
 * déclarations ; `ModeleEnregistre` porte ce qui a été lu sur le disque. L'interface ne doit jamais
 * présenter les deux du même ton — la v1 les confondait et calculait des VRAM à partir d'un nom.
 */

export type FormatModele = 'gguf' | 'safetensors';

/** Filtres de format acceptés par la recherche Hub — étiquettes déclaratives, pas des vérifications. */
export type FormatRecherche = 'gguf' | 'awq' | 'gptq' | 'safetensors';

export type TriRecherche = 'downloads' | 'likes' | 'created_at' | 'last_modified' | 'trending_score';

export type Ordre = 'desc' | 'asc';

/** Un fichier du dépôt. `etiquette` vient du nom de fichier : une intention, jamais un fait. */
export interface FichierDepot {
  nom: string;
  taille_octets: number | null;
  etiquette: string | null;
}

export interface MetadonneesAnnoncees {
  architecture: string | null;
  contexte: number | null;
  nb_parametres: number | null;
}

export interface ResultatRecherche {
  depot: string;
  nom: string;
  auteur: string | null;
  telechargements: number | null;
  mentions: number | null;
  tendance: number | null;
  modifie_le: string | null;
  gated: boolean;
  tache: string | null;
  etiquettes: string[];
  formats: FormatModele[];
  fichiers_gguf: FichierDepot[];
  taille_totale_octets: number | null;
  annonce: MetadonneesAnnoncees;
  deja_telecharge: boolean;
}

export interface PageRecherche {
  resultats: ResultatRecherche[];
  page: number;
  taille_page: number;
  fin_atteinte: boolean;
}

export type EtatTelechargement = 'en_attente' | 'en_cours' | 'termine' | 'annule' | 'interrompu' | 'erreur';

export interface Telechargement {
  identifiant: string;
  depot: string;
  fichier: string | null;
  revision: string;
  chemin: string;
  etat: EtatTelechargement;
  octets_recus: number;
  /** `null` tant que le Hub n'a pas annoncé les tailles : mieux vaut pas de pourcentage qu'un faux. */
  octets_totaux: number | null;
  erreur: string | null;
  remediation: string | null;
  demarre_le: string;
  maj_le: string;
  termine_le: string | null;
  /** dérivé — `null` quand le total est inconnu. */
  progression: number | null;
}

/**
 * Une entrée du registre local. Un champ `null` signifie « pas encore mesuré », jamais « estimé » :
 * `nb_couches` absent veut dire que l'en-tête n'a pas été lu, pas qu'on suppose une valeur.
 */
export interface ModeleEnregistre {
  id: string;
  depot: string;
  fichier: string | null;
  chemin: string;
  format: FormatModele;
  taille_octets: number;
  quantification: string | null;
  architecture: string | null;
  nb_couches: number | null;
  contexte_max: number | null;
  ajoute_le: string;
}

export interface ResumeSynchronisation {
  entrees_supprimees: string[];
  entrees_ajoutees: string[];
  dossiers_ignores: string[];
}
