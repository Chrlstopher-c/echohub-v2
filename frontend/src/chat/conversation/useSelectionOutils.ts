/*
 * État de la sélection d'outils d'une conversation.
 *
 * Deux sources, deux replis distincts et VISIBLES :
 *   - le catalogue vient de `GET /chat/outils` ; à défaut, le catalogue local sert, sans coûts
 *     mesurés — l'écran fonctionne, les tokens affichent « — » ;
 *   - la sélection vient de la conversation ; à défaut, tout est actif et `persistee` passe à
 *     `false` : l'écran DIT que les choix ne survivront pas, il ne fait pas semblant d'enregistrer.
 *
 * Chaque bascule écrit immédiatement : une sélection d'outils n'a pas de brouillon, l'état coché
 * est l'état voulu. L'échec d'écriture recharge la vérité du serveur plutôt que de garder un
 * affichage que la persistance a refusé.
 */

import { useCallback, useEffect, useState } from 'react';
import { journal } from '../api/journal';
import { ecrireSelectionOutils, lireSelectionOutils, listerOutilsDisponibles } from './api-outils';
import { CATALOGUE_OUTILS, type OutilDisponible } from './outils-catalogue';

export interface EtatSelectionOutils {
  readonly catalogue: readonly OutilDisponible[];
  /** Noms actifs. `null` n'existe pas ici : « tous » est déjà résolu en liste pleine. */
  readonly actifs: ReadonlySet<string>;
  /** `false` tant que le backend ne sert pas la sélection : les choix ne survivront pas. */
  readonly persistee: boolean;
  readonly basculer: (nom: string) => void;
  readonly basculerGroupe: (noms: readonly string[], activer: boolean) => void;
}

function tous(catalogue: readonly OutilDisponible[]): Set<string> {
  return new Set(catalogue.map((outil) => outil.nom));
}

/** Applique une sélection serveur (`null` = tous) sur le catalogue affiché. */
function resoudre(catalogue: readonly OutilDisponible[], selection: readonly string[] | null): Set<string> {
  if (selection === null) {
    return tous(catalogue);
  }
  const connus = tous(catalogue);
  return new Set(selection.filter((nom) => connus.has(nom)));
}

function useCatalogue(): readonly OutilDisponible[] {
  const [catalogue, setCatalogue] = useState<readonly OutilDisponible[]>(CATALOGUE_OUTILS);
  useEffect((): (() => void) => {
    const controleur = new AbortController();
    listerOutilsDisponibles(controleur.signal)
      .then((liste): void => {
        if (liste.length > 0) {
          setCatalogue(liste);
        }
      })
      .catch((cause: unknown): void => {
        if (!controleur.signal.aborted) {
          // Repli attendu tant que la route n'existe pas : information, pas erreur.
          journal.avertissement('catalogue des outils non servi, catalogue local utilisé', cause);
        }
      });
    return (): void => controleur.abort();
  }, []);
  return catalogue;
}

interface Poseurs {
  poserActifs: (actifs: ReadonlySet<string>) => void;
  poserPersistee: (persistee: boolean) => void;
}

/** Lit la sélection de la conversation et pose l'état — ou le mode dégradé, visiblement. */
function useLectureSelection(
  conversationId: string | null,
  catalogue: readonly OutilDisponible[],
  { poserActifs, poserPersistee }: Poseurs,
): void {
  useEffect((): (() => void) | undefined => {
    if (conversationId === null) {
      return undefined;
    }
    const controleur = new AbortController();
    lireSelectionOutils(conversationId, controleur.signal)
      .then((selection): void => {
        poserActifs(resoudre(catalogue, selection.outils_actifs));
        poserPersistee(true);
      })
      .catch((cause: unknown): void => {
        if (!controleur.signal.aborted) {
          journal.avertissement('sélection d’outils non servie, défaut « tous » affiché', cause);
          poserActifs(tous(catalogue));
          poserPersistee(false);
        }
      });
    return (): void => controleur.abort();
    // `poserActifs`/`poserPersistee` sont des setters d'état, stables par contrat React.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, catalogue]);
}

/* Écrit, et en cas de refus relit la vérité du serveur : jamais d'état coché non persisté. */
function ecrireOuRelire(
  conversationId: string,
  catalogue: readonly OutilDisponible[],
  prochains: ReadonlySet<string>,
  poserActifs: (actifs: ReadonlySet<string>) => void,
): void {
  ecrireSelectionOutils(conversationId, [...prochains]).catch((cause: unknown): void => {
    journal.erreur('écriture de la sélection d’outils refusée', cause);
    lireSelectionOutils(conversationId)
      .then((selection): void => poserActifs(resoudre(catalogue, selection.outils_actifs)))
      .catch((relecture: unknown): void => journal.erreur('relecture de la sélection impossible', relecture));
  });
}

function basculee(actifs: ReadonlySet<string>, nom: string): Set<string> {
  const prochains = new Set(actifs);
  if (prochains.has(nom)) {
    prochains.delete(nom);
  } else {
    prochains.add(nom);
  }
  return prochains;
}

function grouper(actifs: ReadonlySet<string>, noms: readonly string[], activer: boolean): Set<string> {
  const prochains = new Set(actifs);
  for (const nom of noms) {
    if (activer) {
      prochains.add(nom);
    } else {
      prochains.delete(nom);
    }
  }
  return prochains;
}

export function useSelectionOutils(conversationId: string | null): EtatSelectionOutils {
  const catalogue = useCatalogue();
  const [actifs, setActifs] = useState<ReadonlySet<string>>(() => tous(CATALOGUE_OUTILS));
  const [persistee, setPersistee] = useState<boolean>(false);
  useLectureSelection(conversationId, catalogue, { poserActifs: setActifs, poserPersistee: setPersistee });

  const appliquer = useCallback(
    (prochains: ReadonlySet<string>): void => {
      setActifs(prochains);
      if (conversationId !== null && persistee) {
        ecrireOuRelire(conversationId, catalogue, prochains, setActifs);
      }
    },
    [conversationId, persistee, catalogue],
  );

  return {
    catalogue,
    actifs,
    persistee,
    basculer: useCallback((nom) => appliquer(basculee(actifs, nom)), [actifs, appliquer]),
    basculerGroupe: useCallback(
      (noms, activer) => appliquer(grouper(actifs, noms, activer)),
      [actifs, appliquer],
    ),
  };
}
