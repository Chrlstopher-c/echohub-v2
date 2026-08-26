/*
 * État de l'atelier : quel artefact est ouvert, à quelle version.
 *
 * La sélection ne retient que des IDENTIFIANTS ; tout le reste se dérive du catalogue à chaque
 * rendu. C'est ce qui rend l'état robuste au changement de branche : si le chemin affiché ne
 * porte plus l'artefact ouvert (bascule de variante, changement de conversation), la dérivation
 * rend `null` et le panneau se ferme tout seul — aucun artefact fantôme d'une autre branche.
 */

import { useCallback, useMemo, useState } from 'react';
import { collecterArtefacts, type ArtefactCatalogue, type MessageCollectable } from './versions';
import type { VersionArtefact } from './detection';

interface Selection {
  readonly artefactId: string;
  readonly version: number;
}

export interface AtelierOuvert {
  readonly artefact: ArtefactCatalogue;
  readonly version: VersionArtefact;
}

export interface EtatAtelier {
  readonly catalogue: ReadonlyMap<string, ArtefactCatalogue>;
  readonly ouvert: AtelierOuvert | null;
  readonly ouvrir: (version: VersionArtefact) => void;
  readonly choisirVersion: (numero: number) => void;
  readonly fermer: () => void;
}

function deriver(catalogue: Map<string, ArtefactCatalogue>, selection: Selection | null): AtelierOuvert | null {
  if (selection === null) {
    return null;
  }
  const artefact = catalogue.get(selection.artefactId);
  const version = artefact?.versions.find((v) => v.version === selection.version);
  if (artefact === undefined || version === undefined) {
    return null;
  }
  return { artefact, version };
}

export function useAtelier(messages: readonly MessageCollectable[], brouillon: string | null): EtatAtelier {
  const [selection, setSelection] = useState<Selection | null>(null);
  // Mémoïsé sur les références : le fil remplace son tableau de messages à chaque mutation, la
  // collecte ne recoupe donc jamais un rendu où rien n'a changé.
  const catalogue = useMemo(() => collecterArtefacts(messages, brouillon), [messages, brouillon]);
  const ouvert = useMemo(() => deriver(catalogue, selection), [catalogue, selection]);

  const ouvrir = useCallback((version: VersionArtefact): void => {
    setSelection({ artefactId: version.artefact_id, version: version.version });
  }, []);

  const choisirVersion = useCallback((numero: number): void => {
    setSelection((courante) => (courante === null ? null : { ...courante, version: numero }));
  }, []);

  const fermer = useCallback((): void => setSelection(null), []);

  return { catalogue, ouvert, ouvrir, choisirVersion, fermer };
}
