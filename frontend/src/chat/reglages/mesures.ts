/*
 * Ce que les réponses de CETTE conversation disent du plafond — par la mesure, pas par le principe.
 *
 * Deux grandeurs seulement, et elles ne se mélangent jamais :
 *
 * 1. **Des jetons mesurés par le moteur** (`tokens_generes`, `null` quand il ne les rapporte pas).
 *    C'est la seule grandeur comparable au plafond, qui est lui aussi un nombre de jetons.
 * 2. **Des caractères comptés ici** dans les blocs `<think>`. Un caractère n'est pas un jeton et
 *    aucune conversion n'est appliquée : le rapport entre les deux dépend du vocabulaire du modèle,
 *    et l'inventer serait exactement l'estimation que la v2 supprime. Cette part sert à montrer OÙ
 *    est passé le texte, jamais à chiffrer un coût en jetons — c'est le panneau de contexte qui
 *    mesure le raisonnement en jetons, avec le tokenizer du modèle chargé.
 *
 * Le découpage des blocs reproduit `separer_raisonnement` de
 * `backend/inference/engines_adapters/contrat.py` : mêmes balises littérales, balises comptées DANS
 * le raisonnement (ce sont des jetons réels renvoyés au modèle au tour suivant), et bloc jamais
 * refermé courant jusqu'à la fin du texte. Un modèle qui baliserait autrement compte pour zéro
 * plutôt que d'être deviné.
 */

import type { MessageChat } from '../api/contrats';

const BALISE_OUVRANTE = '<think>';
const BALISE_FERMANTE = '</think>';

export interface PartRaisonnement {
  readonly caracteres: number;
  /** Bloc ouvert et jamais refermé : la génération s'est arrêtée pendant le raisonnement. */
  readonly nonReferme: boolean;
}

export interface MesureReponse {
  readonly id: string;
  /** Jetons rapportés par le moteur. `null` = non mesuré, et alors rien n'est déduit. */
  readonly tokens: number | null;
  readonly caracteres: number;
  readonly raisonnement: PartRaisonnement;
}

/** Réponse dont le moteur a rapporté les jetons : le seul cas comparable à un plafond en jetons. */
export interface ReponseMesuree extends MesureReponse {
  readonly tokens: number;
}

export interface BilanReponses {
  readonly reponses: number;
  /** Réponses dont le moteur a rapporté un nombre de jetons. */
  readonly mesurees: number;
  /** La plus longue des réponses MESURÉES — celle qui a le plus approché le plafond. */
  readonly plusLongue: ReponseMesuree | null;
  /** Réponses dont le compte de jetons vaut exactement le plafond courant. */
  readonly auPlafond: number;
}

export function mesurerRaisonnement(contenu: string): PartRaisonnement {
  let caracteres = 0;
  let reste = contenu;
  // Borne explicite : chaque tour consomme au moins une balise ouvrante.
  const toursMax = Math.floor(contenu.length / BALISE_OUVRANTE.length) + 1;
  for (let tour = 0; tour < toursMax; tour += 1) {
    const debut = reste.indexOf(BALISE_OUVRANTE);
    if (debut < 0) {
      return { caracteres, nonReferme: false };
    }
    const apres = reste.slice(debut);
    const fin = apres.indexOf(BALISE_FERMANTE);
    if (fin < 0) {
      return { caracteres: caracteres + apres.length, nonReferme: true };
    }
    const coupe = fin + BALISE_FERMANTE.length;
    caracteres += coupe;
    reste = apres.slice(coupe);
  }
  return { caracteres, nonReferme: false };
}

function mesurer(message: MessageChat): MesureReponse {
  return {
    id: message.id,
    tokens: message.tokens_generes,
    caracteres: message.contenu.length,
    raisonnement: mesurerRaisonnement(message.contenu),
  };
}

/**
 * Le maximum est cherché parmi les seules réponses mesurées, et le type le porte : une réponse sans
 * compte de jetons ne peut pas être comparée au plafond, elle n'entre donc jamais dans ce résultat.
 */
function plusLongue(mesures: readonly MesureReponse[]): ReponseMesuree | null {
  let retenue: ReponseMesuree | null = null;
  for (const mesure of mesures) {
    const tokens = mesure.tokens;
    if (tokens !== null && (retenue === null || tokens > retenue.tokens)) {
      retenue = { ...mesure, tokens };
    }
  }
  return retenue;
}

/**
 * `plafond` à `null` (aucun plafond posé) laisse `auPlafond` à zéro : sans plafond, aucune réponse
 * ne peut avoir été coupée par lui.
 */
export function bilanReponses(messages: readonly MessageChat[], plafond: number | null): BilanReponses {
  const mesures = messages.filter((message) => message.role === 'assistant').map(mesurer);
  const mesurees = mesures.filter((mesure) => mesure.tokens !== null);
  return {
    reponses: mesures.length,
    mesurees: mesurees.length,
    plusLongue: plusLongue(mesures),
    auPlafond: plafond === null ? 0 : mesurees.filter((mesure) => mesure.tokens === plafond).length,
  };
}
