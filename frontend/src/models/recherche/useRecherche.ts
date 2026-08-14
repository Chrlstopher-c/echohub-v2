/*
 * État de la recherche Hugging Face.
 *
 * Une seule requête en vol à la fois : toute frappe annule la précédente. Sans cela, deux réponses
 * arrivées dans le désordre afficheraient le résultat de la requête la plus lente, pas de la
 * dernière tapée — un bug qui ne se voit qu'en réseau lent, donc jamais en développement.
 */

import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import { messageErreur } from '../api/client';
import { CRITERE_INITIAL, rechercher, type CritereRecherche } from '../api/recherche';
import type { Capacite, FormatRecherche, PageRecherche, TriRecherche } from '../api/types';

/**
 * Frappe au clavier : assez court pour rester vif, assez long pour ne pas partir à chaque lettre.
 *
 * Le délai couvre TOUTE modification du critère, filtres compris : cocher trois capacités d'affilée
 * ne déclenche qu'une requête. C'est le comportement voulu pour une sélection multiple, où l'on
 * clique plusieurs fois avant d'attendre un résultat.
 */
const DELAI_SAISIE_MS = 300;

/** Les seules mutations possibles du critère : l'écran ne le reconstruit jamais lui-même. */
export interface ActionsRecherche {
  definirRequete: (requete: string) => void;
  basculerFormat: (format: FormatRecherche) => void;
  basculerCapacite: (capacite: Capacite) => void;
  effacerCapacites: () => void;
  definirTri: (tri: TriRecherche) => void;
  allerPage: (page: number) => void;
}

export interface EtatRecherche extends ActionsRecherche {
  critere: CritereRecherche;
  page: PageRecherche | null;
  chargement: boolean;
  erreur: string | null;
}

interface Resultat {
  page: PageRecherche | null;
  chargement: boolean;
  erreur: string | null;
}

/**
 * Ajout ou retrait d'un membre d'une sélection multiple.
 *
 * Une seule implémentation pour les formats et les capacités : ce sont deux filtres du même
 * critère, ils changent ensemble et leur règle de bascule est la même. La spécialiser deux fois
 * ferait deux endroits où corriger le jour où l'on ordonne la sélection.
 */
function bascule<T>(selection: readonly T[], valeur: T): T[] {
  return selection.includes(valeur) ? selection.filter((item) => item !== valeur) : [...selection, valeur];
}

/** Exécute la recherche après le délai de frappe, en annulant tout appel encore en vol. */
function useResultat(critere: CritereRecherche): Resultat {
  const [page, setPage] = useState<PageRecherche | null>(null);
  const [chargement, setChargement] = useState<boolean>(true);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    const controleur = new AbortController();
    setChargement(true);
    const minuteur = window.setTimeout(() => {
      rechercher(critere, controleur.signal)
        .then((resultat) => {
          setPage(resultat);
          setErreur(null);
        })
        .catch((cause: unknown) => {
          if (!controleur.signal.aborted) {
            setErreur(messageErreur(cause));
          }
        })
        .finally(() => {
          if (!controleur.signal.aborted) {
            setChargement(false);
          }
        });
    }, DELAI_SAISIE_MS);

    return (): void => {
      window.clearTimeout(minuteur);
      controleur.abort();
    };
  }, [critere]);

  return { page, chargement, erreur };
}

/*
 * Deux invariants tiennent dans ces six fonctions :
 *
 * - toute modification de filtre ramène à la première page — garder la page 4 d'une autre recherche
 *   afficherait un vide inexplicable ;
 * - les familles de filtres (formats, capacités) vivent côte à côte dans le même critère : elles se
 *   cumulent au lieu de se remplacer, et l'une ne réinitialise jamais l'autre.
 */
function useActions(setCritere: Dispatch<SetStateAction<CritereRecherche>>): ActionsRecherche {
  const definirRequete = useCallback((requete: string): void => {
    setCritere((actuel) => ({ ...actuel, requete, page: 0 }));
  }, [setCritere]);

  const basculerFormat = useCallback((format: FormatRecherche): void => {
    setCritere((actuel) => ({ ...actuel, formats: bascule(actuel.formats, format), page: 0 }));
  }, [setCritere]);

  const basculerCapacite = useCallback((capacite: Capacite): void => {
    setCritere((actuel) => ({ ...actuel, capacites: bascule(actuel.capacites, capacite), page: 0 }));
  }, [setCritere]);

  // Sélection déjà vide : on rend le critère inchangé pour ne pas relancer une requête identique.
  const effacerCapacites = useCallback((): void => {
    setCritere((actuel) => (actuel.capacites.length === 0 ? actuel : { ...actuel, capacites: [], page: 0 }));
  }, [setCritere]);

  const definirTri = useCallback((tri: TriRecherche): void => {
    setCritere((actuel) => ({ ...actuel, tri, page: 0 }));
  }, [setCritere]);

  const allerPage = useCallback((numero: number): void => {
    setCritere((actuel) => ({ ...actuel, page: Math.max(0, numero) }));
  }, [setCritere]);

  return { definirRequete, basculerFormat, basculerCapacite, effacerCapacites, definirTri, allerPage };
}

export function useRecherche(): EtatRecherche {
  const [critere, setCritere] = useState<CritereRecherche>(CRITERE_INITIAL);
  const resultat = useResultat(critere);
  const actions = useActions(setCritere);
  return { critere, ...resultat, ...actions };
}
