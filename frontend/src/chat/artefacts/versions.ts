/*
 * Catalogue des artefacts d'une conversation, reconstruit depuis les MESSAGES.
 *
 * Aucune route dédiée : chaque version est un appel de `creer_artefact` persisté dans le texte du
 * message qui l'a produite — le même principe qui rend les appels d'outils relisibles après
 * rechargement (`backend/inference/harnais_outils.py`). Lire le chemin de branche affiché suffit
 * donc à retrouver les versions, ET garantit que l'atelier montre exactement ce que cette branche
 * a réellement produit : une version créée dans une branche abandonnée n'existe pas ici.
 */

import { segmenterReponse } from '../raisonnement/extraction';
import { versionDepuisSegment, type TypeArtefact, type VersionArtefact } from './detection';

export interface ArtefactCatalogue {
  readonly artefact_id: string;
  /** Titre et type de la DERNIÈRE version : c'est elle que le modèle considère comme courante. */
  readonly titre: string;
  readonly type: TypeArtefact | 'inconnu';
  /** Versions dans l'ordre croissant de numéro. */
  readonly versions: readonly VersionArtefact[];
}

/** La forme minimale dont la collecte a besoin — évite de dépendre du contrat complet des messages. */
export interface MessageCollectable {
  readonly role: string;
  readonly contenu: string;
}

function versionsDuTexte(texte: string): VersionArtefact[] {
  const trouvees: VersionArtefact[] = [];
  for (const segment of segmenterReponse(texte).raisonnements) {
    const version = versionDepuisSegment(segment);
    if (version !== null) {
      trouvees.push(version);
    }
  }
  return trouvees;
}

function classer(versions: Map<string, VersionArtefact[]>, version: VersionArtefact): void {
  const existantes = versions.get(version.artefact_id) ?? [];
  // Un rejeu peut réémettre le même numéro : la rencontre la plus récente remplace l'ancienne,
  // parce que c'est elle que le serveur a réellement retenue en dernier.
  const sansDoublon = existantes.filter((v) => v.version !== version.version);
  sansDoublon.push(version);
  versions.set(version.artefact_id, sansDoublon);
}

/**
 * Collecte les artefacts du chemin affiché, brouillon de streaming compris — une version dont la
 * sortie vient de se refermer doit être ouvrable AVANT que le message soit persisté, sinon la
 * carte fraîchement apparue serait un bouton mort le temps du tour.
 */
export function collecterArtefacts(
  messages: readonly MessageCollectable[],
  brouillon: string | null,
): Map<string, ArtefactCatalogue> {
  const parArtefact = new Map<string, VersionArtefact[]>();
  for (const message of messages) {
    if (message.role !== 'assistant') {
      continue;
    }
    for (const version of versionsDuTexte(message.contenu)) {
      classer(parArtefact, version);
    }
  }
  for (const version of versionsDuTexte(brouillon ?? '')) {
    classer(parArtefact, version);
  }
  const catalogue = new Map<string, ArtefactCatalogue>();
  for (const [id, versions] of parArtefact) {
    const ordonnees = [...versions].sort((a, b) => a.version - b.version);
    const derniere = ordonnees[ordonnees.length - 1];
    if (derniere === undefined) {
      continue;
    }
    catalogue.set(id, { artefact_id: id, titre: derniere.titre, type: derniere.type, versions: ordonnees });
  }
  return catalogue;
}
