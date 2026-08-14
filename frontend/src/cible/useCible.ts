/*
 * Rassemble les mesures des trois domaines et en fait une `CibleChargement`.
 *
 * Les quatre appels partent ensemble : ils sont indépendants, et les enchaîner ferait attendre
 * l'utilisateur pour rien. Trois d'entre eux sont tolérants à l'échec — moteurs et état d'inférence
 * ne font qu'enrichir le profil ; leur absence donne un plan plus prudent, pas une erreur. Les
 * métadonnées et le profil machine, eux, sont indispensables : sans eux il n'y a rien à planifier.
 *
 * Le profil est relu à CHAQUE sélection, jamais mémorisé : la VRAM libre change dès qu'un modèle
 * est chargé ou éjecté, et planifier sur une mesure périmée est précisément ce qui produisait les
 * échecs silencieux de la v1.
 */

import { useCallback, useRef, useState } from 'react';

import type { CibleChargement } from '../chat';
import {
  lireEtatInference,
  lireEtatMoteurs,
  lireProfilMachine,
  metadonneesModele,
  type ModeleEnregistre,
} from '../shared/api';
import { construireCible, type RefusCible } from './conversion';

export interface EtatCible {
  readonly cible: CibleChargement | null;
  /** Refus nommé : ce qui manque et quoi faire. Distinct d'une erreur réseau. */
  readonly refus: RefusCible | null;
  readonly erreur: string | null;
  readonly enCours: boolean;
  readonly choisir: (modele: ModeleEnregistre) => void;
}

function messageDe(cause: unknown): string {
  return cause instanceof Error ? cause.message : 'Erreur inconnue.';
}

export function useCible(): EtatCible {
  const [cible, setCible] = useState<CibleChargement | null>(null);
  const [refus, setRefus] = useState<RefusCible | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  // Une sélection plus récente doit gagner : sans ce compteur, une première requête lente écraserait
  // le résultat d'une seconde plus rapide.
  const generation = useRef(0);

  const choisir = useCallback((modele: ModeleEnregistre): void => {
    const mienne = generation.current + 1;
    generation.current = mienne;
    setEnCours(true);
    setErreur(null);
    setRefus(null);

    const mesurer = async (): Promise<void> => {
      const [gguf, profil, moteurs, statut] = await Promise.all([
        metadonneesModele(modele.id),
        lireProfilMachine(),
        lireEtatMoteurs().catch((): null => null),
        lireEtatInference().catch((): null => null),
      ]);
      if (generation.current !== mienne) {
        return;
      }
      const resultat = construireCible(modele, gguf, profil, moteurs, statut);
      if ('refus' in resultat) {
        setCible(null);
        setRefus(resultat.refus);
        return;
      }
      setRefus(null);
      setCible(resultat.cible);
    };

    void mesurer()
      .catch((cause: unknown): void => {
        if (generation.current !== mienne) return;
        setCible(null);
        setErreur(messageDe(cause));
      })
      .finally((): void => {
        if (generation.current === mienne) setEnCours(false);
      });
  }, []);

  return { cible, refus, erreur, enCours, choisir };
}
