/*
 * Bouton « copier », et le seul point de l'interface où l'échec du presse-papiers est visible.
 *
 * Le retour se fait par le bouton lui-même (l'icône devient une coche pendant 1,2 s) plutôt que par
 * une notification : il est là où l'œil se trouve déjà, et il ne recouvre rien.
 *
 * Le refus, lui, ne peut pas se contenter d'une icône : il faut dire quoi faire. Hors contexte
 * sécurisé — l'interface ouverte depuis une autre machine du réseau — aucune API ne peut réussir,
 * seule la sélection manuelle reste. Une copie perdue en silence ferait coller autre chose.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { BoutonAction } from './BoutonAction';
import { IconeCoche, IconeCopier } from './icones';
import { copierTexte } from './presse-papiers';

/* Assez long pour être vu, trop court pour distraire pendant qu'on lit la suite du fil. */
const DUREE_RETOUR_MS = 1200;

type EtatCopie = 'repos' | 'copiee' | 'refusee';

function useCopie(texte: string): { etat: EtatCopie; copier: () => void } {
  const [etat, setEtat] = useState<EtatCopie>('repos');
  const minuteur = useRef<number | undefined>(undefined);

  // Un seul minuteur, toujours nettoyé : pas de mise à jour d'état après démontage.
  useEffect((): (() => void) => (): void => window.clearTimeout(minuteur.current), []);

  const copier = useCallback((): void => {
    // Promesse volontairement non attendue : le clic ne bloque pas, le résultat arrive par l'état.
    void copierTexte(texte).then((resultat): void => {
      setEtat(resultat === 'copiee' ? 'copiee' : 'refusee');
      window.clearTimeout(minuteur.current);
      minuteur.current = window.setTimeout((): void => setEtat('repos'), DUREE_RETOUR_MS);
    });
  }, [texte]);

  return { etat, copier };
}

export interface BoutonCopierProps {
  texte: string;
}

export function BoutonCopier({ texte }: BoutonCopierProps): ReactElement {
  const { etat, copier } = useCopie(texte);
  return (
    <>
      <BoutonAction
        libelle="Copier le message"
        titre={etat === 'refusee' ? 'Copie refusée par le navigateur' : 'Copier le message'}
        desactive={false}
        onClic={copier}
      >
        {etat === 'copiee' ? <IconeCoche /> : <IconeCopier />}
      </BoutonAction>
      {etat === 'refusee' && (
        <span className="pl-1 pr-0.5 text-2xs text-caution">
          Copie refusée — sélectionner le texte, puis Ctrl+C.
        </span>
      )}
    </>
  );
}
