/*
 * Contrats de données servis par le backend, transcrits en TypeScript.
 *
 * Ces types décrivent ce que le backend ENVOIE, ils ne redéfinissent aucune règle : toute valeur
 * du plan arrive accompagnée de sa justification, et l'interface se contente de la rendre.
 * Sources : `backend/chat/modeles.py`, `backend/inference/planner/{entrees,plan}.py`,
 * `backend/inference/engines_adapters/{contrat,journal,superviseur}.py`.
 *
 * Les champs optionnels côté pydantic sont sérialisés à `null`, jamais absents : ils sont donc
 * typés `| null` et non `?`. Les corps de requête, eux, utilisent `?` — un champ omis y a un sens.
 */

/* ------------------------------------------------------------------ planificateur : entrées */

export type Moteur = 'llama.cpp' | 'vllm';
export type FormatModele = 'gguf' | 'safetensors';
export type TypeCacheKV = 'f16' | 'q8_0' | 'q4_0';
export type PlateformePlan = 'linux_natif' | 'wsl2' | 'windows';

/** Métadonnées LUES dans le modèle — jamais déduites de son nom de fichier. */
export interface MetadonneesModele {
  identifiant: string;
  format: FormatModele;
  architecture: string;
  taille_octets: number;
  nombre_couches: number;
  dimension_embedding: number;
  dimension_ffn: number;
  nombre_tetes_attention: number;
  nombre_tetes_kv: number;
  dimension_tete: number | null;
  contexte_entrainement_max: number;
  taille_vocabulaire: number;
  quantification: string | null;
  est_moe: boolean;
}

export interface ModeleCharge {
  identifiant: string;
  moteur: Moteur;
  vram_octets: number;
}

/** Profil au format attendu par le planificateur (distinct de celui du domaine `system`). */
export interface ProfilMachinePlan {
  plateforme: PlateformePlan;
  index_gpu: number;
  nom_gpu: string;
  vram_totale_octets: number;
  vram_libre_octets: number;
  ram_libre_octets: number;
  moteurs_disponibles: Moteur[];
  modeles_charges: ModeleCharge[];
  capacite_calcul: [number, number] | null;
}

/** Ce que l'utilisateur demande. Rien n'est garanti : tout est plafonné par la machine. */
export interface PreferencesUtilisateur {
  contexte?: number | null;
  batch?: number | null;
  couches_gpu?: number | null;
  type_cache_kv?: TypeCacheKV;
  moteur?: Moteur | null;
  flash_attention?: boolean;
  autoriser_memoire_unifiee?: boolean;
  ratio_fragmentation?: number;
}

export interface DemandeDeChargement {
  metadonnees: MetadonneesModele;
  profil: ProfilMachinePlan;
  preferences: PreferencesUtilisateur;
}

/* ------------------------------------------------------------------- planificateur : sortie */

/** Une valeur du plan et la phrase qui l'explique. `plafonnee` distingue la machine de l'humain. */
export interface ValeurJustifiee<T> {
  valeur: T;
  justification: string;
  plafonnee: boolean;
  valeur_demandee: T | null;
}

export interface PosteMemoire {
  libelle: string;
  octets: number;
  justification: string;
}

export interface BudgetMemoire {
  vram_disponible_octets: number;
  postes: PosteMemoire[];
  ram_requise_octets: number;
  ram_disponible_octets: number;
}

export interface VariableEnvironnement {
  nom: string;
  valeur: string;
  justification: string;
}

/** Variable délibérément NON posée : une absence décidée vaut d'être affichée comme un réglage. */
export interface VariableRefusee {
  nom: string;
  raison: string;
}

export interface EjectionRequise {
  identifiant: string;
  moteur: Moteur;
  vram_liberee_octets: number;
  raison: string;
}

export interface PlanDeChargement {
  identifiant_modele: string;
  niveau_degradation: number;
  moteur: ValeurJustifiee<Moteur>;
  couches_gpu: ValeurJustifiee<number>;
  couches_totales: number;
  contexte: ValeurJustifiee<number>;
  batch: ValeurJustifiee<number>;
  type_cache_kv: ValeurJustifiee<TypeCacheKV>;
  flash_attention: ValeurJustifiee<boolean>;
  utilisation_memoire_gpu: ValeurJustifiee<number> | null;
  variables_environnement: VariableEnvironnement[];
  variables_refusees: VariableRefusee[];
  ejections_requises: EjectionRequise[];
  budget: BudgetMemoire;
  avertissements: string[];
}

export interface ReponsePlan {
  plan: PlanDeChargement;
  justifications: string[];
  avertissements: string[];
}

/* ------------------------------------------------------------------------ pilotage moteurs */

export type EtatMoteurChargement = 'inactif' | 'en_cours' | 'pret' | 'echoue';

/** Qualification d'un échec. Elle existe parce que la v1 remontait le même message pour tout. */
export type CauseEchec =
  | 'vram_insuffisante'
  | 'vram_non_liberee'
  | 'ram_insuffisante'
  | 'contexte_trop_grand'
  | 'architecture_inconnue'
  | 'quantification_incompatible'
  | 'fichier_illisible'
  | 'moteur_absent'
  | 'moteur_sans_cuda'
  | 'plan_incomplet'
  | 'delai_depasse'
  | 'annule'
  | 'indeterminee';

export interface EtatMoteur {
  moteur: Moteur;
  modele: string;
  pret: boolean;
  contexte: number;
  couches_gpu: number;
  port: number | null;
  duree_chargement_s: number;
  vram_avant_octets: number | null;
  vram_apres_octets: number | null;
}

export interface StatutInference {
  etat: EtatMoteurChargement;
  moteur: Moteur | null;
  modele: string | null;
  cause: CauseEchec | null;
  message: string;
  remediation: string;
  session_journal: string | null;
  depuis: string;
  etat_moteur: EtatMoteur | null;
}

export type NiveauEntree = 'info' | 'avertissement' | 'erreur';

/** Un fait daté du chargement : c'est la seule progression honnête dont dispose l'interface. */
export interface EntreeJournal {
  horodatage: string;
  phase: string;
  niveau: NiveauEntree;
  message: string;
}

export interface SessionChargement {
  identifiant: string;
  debut: string;
  fin: string | null;
  duree_s: number | null;
  moteur: string;
  modele: string;
  etat: EtatMoteurChargement;
  cause: CauseEchec | null;
  message: string;
  remediation: string;
  entrees: EntreeJournal[];
}

/* --------------------------------------------------------------------------- domaine chat */

export type RoleMessage = 'system' | 'user' | 'assistant';

export interface ParametresEchantillonnage {
  temperature: number;
  top_p: number;
  top_k: number;
  penalite_repetition: number;
  max_tokens: number;
  sequences_arret: string[];
  graine: number | null;
}

export interface ReglagesConversation {
  prompt_systeme: string;
  parametres: ParametresEchantillonnage;
  historique_max_messages: number | null;
}

export interface MessageChat {
  id: string;
  conversation_id: string;
  role: RoleMessage;
  contenu: string;
  tokens_generes: number | null;
  tokens_par_seconde: number | null;
  cree_le: string;
  modele_id: string | null;
  interrompu: boolean;
}

export interface ResumeConversation {
  id: string;
  titre: string;
  modele_id: string | null;
  cree_le: string;
  maj_le: string;
  archivee: boolean;
  nb_messages: number;
}

export interface ConversationDetaillee {
  conversation: ResumeConversation;
  reglages: ReglagesConversation;
  messages: MessageChat[];
}

export interface MajReglages {
  prompt_systeme?: string;
  parametres?: ParametresEchantillonnage;
  historique_max_messages?: number | null;
}

export interface DemandeGeneration {
  contenu: string;
  modele_id?: string | null;
  parametres?: ParametresEchantillonnage;
}

/* ------------------------------------------------------------------ événements de génération */

export interface EvenementDebut {
  type: 'debut';
  conversation_id: string;
  message_id: string;
  modele_id: string | null;
}

export interface EvenementFragment {
  type: 'fragment';
  texte: string;
}

export interface EvenementFin {
  type: 'fin';
  message_id: string;
  tokens_generes: number | null;
  tokens_par_seconde: number | null;
  duree_ms: number;
  interrompu: boolean;
}

export interface EvenementErreur {
  type: 'erreur';
  code: string;
  message: string;
  remediation: string;
}

export type EvenementFlux = EvenementDebut | EvenementFragment | EvenementFin | EvenementErreur;
