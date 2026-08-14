/*
 * Mise en forme des capacités déduites — la partie « affichage » de la distinction du domaine.
 *
 * Ce module ne déduit rien et ne classe rien : le backend a conclu, et il a publié à la fois le
 * vocabulaire (libellé, définition) et la provenance de chaque conclusion. Ici on se contente de
 * rendre lisible ce qui a été reçu. Une seule chose est écrite localement : le nom français des
 * sources d'indice, que le backend n'expose pas — et il est choisi pour dire à chaque fois d'où
 * vient l'indice, donc pourquoi une capacité est une lecture de déclaration, pas une vérification.
 */

import type { Capacite, DefinitionCapacite, IndiceCapacite, SourceIndice } from '../api/types';

const LIBELLE_SOURCE: Record<SourceIndice, string> = {
  tache: 'tâche déclarée',
  etiquette: 'étiquette',
  nom: 'nom du dépôt',
  description: 'description',
  fichier: 'fichier listé',
};

/** Vocabulaire indexé : le libellé d'un badge se lit sans reparcourir la liste à chaque rendu. */
export type CarteCapacites = ReadonlyMap<Capacite, DefinitionCapacite>;

export function indexerCapacites(definitions: readonly DefinitionCapacite[]): CarteCapacites {
  // Le tableau intermédiaire est typé explicitement : sans lui, le littéral `[cle, valeur]` est
  // élargi en `(Capacite | DefinitionCapacite)[]` et n'est plus une entrée de `Map` valide.
  const entrees: Array<[Capacite, DefinitionCapacite]> = definitions.map((definition) => [
    definition.capacite,
    definition,
  ]);
  return new Map(entrees);
}

/**
 * Libellé publié, ou la valeur brute si le vocabulaire n'a pas pu être chargé.
 *
 * Afficher le code exact (`appel_outils`) reste honnête : c'est ce que le backend a répondu.
 * Fabriquer un libellé de secours côté interface serait inventer un texte que personne n'a publié.
 */
export function libelleCapacite(carte: CarteCapacites, capacite: Capacite): string {
  return carte.get(capacite)?.libelle ?? capacite;
}

/** Définition publiée, `null` quand le vocabulaire manque — l'appelant décide quoi en faire. */
export function definitionCapacite(carte: CarteCapacites, capacite: Capacite): string | null {
  return carte.get(capacite)?.definition ?? null;
}

/** Provenance d'une déduction, une ligne par indice : « étiquette « vision » ». */
export function provenance(indices: readonly IndiceCapacite[]): string[] {
  return indices.map((indice) => `${LIBELLE_SOURCE[indice.source]} « ${indice.valeur} »`);
}
