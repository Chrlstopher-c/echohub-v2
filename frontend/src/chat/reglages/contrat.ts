/*
 * Forme des réglages telle que ce panneau la pilote, dérivée du contrat du domaine.
 *
 * Deux champs ont changé côté backend (`backend/chat/modeles.py`) sans que `chat/api/contrats.ts`
 * l'ait encore suivi : `max_tokens` vaut désormais `number | null` (null = aucun plafond, et c'est
 * le défaut), et le patch des paramètres est PARTIEL — seuls les champs présents sont appliqués.
 * Les types sont donc dérivés de l'existant plutôt que recopiés : tout ce qui n'a pas bougé reste
 * défini à un seul endroit, et le jour où `contrats.ts` portera `number | null`, ces déclarations
 * resteront exactes sans retouche. Le rapport de livraison décrit la reprise à faire là-bas.
 */

import type {
  ParametresEchantillonnage as ParametresContrat,
  ReglagesConversation as ReglagesContrat,
} from '../api/contrats';

/**
 * `max_tokens` à `null` n'est pas une absence de valeur : c'est le réglage « aucun plafond posé
 * ici », et le moteur s'arrête alors sur la fenêtre de contexte qu'il sert. Il faut donc pouvoir
 * l'envoyer explicitement, pas seulement omettre le champ.
 */
export type ParametresConversation = Omit<ParametresContrat, 'max_tokens'> & {
  max_tokens: number | null;
};

export type Reglages = Omit<ReglagesContrat, 'parametres'> & {
  parametres: ParametresConversation;
};

/**
 * Patch partiel : la PRÉSENCE d'une clé vaut demande d'écriture, `null` compris. `max_tokens: null`
 * et `graine: null` effacent la valeur, alors qu'une clé absente laisse l'existant intact — c'est
 * `MajParametres` côté pydantic, qui distingue les deux par `exclude_unset`.
 */
export type MajParametres = Partial<ParametresConversation>;

export interface MajReglages {
  prompt_systeme?: string;
  parametres?: MajParametres;
  historique_max_messages?: number | null;
}

export type CleParametre = keyof ParametresConversation;

/** Tout ce que ce panneau sait modifier : les paramètres, plus le prompt système. */
export type CleReglage = 'prompt_systeme' | CleParametre;
