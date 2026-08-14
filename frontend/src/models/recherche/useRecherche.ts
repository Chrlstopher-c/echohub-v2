/*
 * État de la recherche Hugging Face.
 *
 * Une seule requête en vol à la fois : toute frappe annule la précédente. Sans cela, deux réponses
 * arrivées dans le désordre afficheraient le résultat de la requête la plus lente, pas de la
 * dernière tapée — un bug qui ne se voit qu'en réseau lent, donc jamais en développement.
 */

import { useCallback, useEffect, useState } from 'react';
import { messageErreur } from '../api/client';
import { CRITERE_INITIAL, rechercher, type CritereRecherche } from '../api/recherche';
import type { FormatRecherche, PageRecherche, TriRecherche } from '../api/types';

/** Frappe au clavier : assez court pour rester vif, assez long pour ne pas partir à chaque lettre. */
const DELAI_SAISIE_MS = 300;

export interface EtatRecherche {
  critere: CritereRecherche;
  page: PageRecherche | null;
  chargement: boolean;
  erreur: string | null;
  definirRequete: (requete: string) => void;
  basculerFormat: (format: FormatRecherche) => void;
  definirTri: (tri: TriRecherche) => void;
  allerPage: (page: number) => void;
}

interface Resultat {
  page: PageRecherche | null;
  chargement: boolean;
  erreur: string | null;
}

function avecFormat(formats: readonly FormatRecherche[], format: FormatRecherche): FormatRecherche[] {
  return formats.includes(format) ? formats.filter((item) => item !== format) : [...formats, format];
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

export function useRecherche(): EtatRecherche {
  const [critere, setCritere] = useState<CritereRecherche>(CRITERE_INITIAL);
  const resultat = useResultat(critere);

  // Toute modification de filtre ramène à la première page : garder la page 4 d'une autre
  // recherche afficherait un vide inexplicable.
  const definirRequete = useCallback((requete: string): void => {
    setCritere((actuel) => ({ ...actuel, requete, page: 0 }));
  }, []);

  const basculerFormat = useCallback((format: FormatRecherche): void => {
    setCritere((actuel) => ({ ...actuel, formats: avecFormat(actuel.formats, format), page: 0 }));
  }, []);

  const definirTri = useCallback((tri: TriRecherche): void => {
    setCritere((actuel) => ({ ...actuel, tri, page: 0 }));
  }, []);

  const allerPage = useCallback((numero: number): void => {
    setCritere((actuel) => ({ ...actuel, page: Math.max(0, numero) }));
  }, []);

  return { critere, ...resultat, definirRequete, basculerFormat, definirTri, allerPage };
}
