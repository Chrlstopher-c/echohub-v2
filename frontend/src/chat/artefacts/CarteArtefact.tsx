import { useState } from 'react';
import type { ReactElement } from 'react';
import { cn } from '../../shared/design';
import type { ArtefactPresente } from './detection';
import { IconeFichier } from './icones';
import { ModaleArtefact } from './ModaleArtefact';

const UNITES = ['o', 'Kio', 'Mio', 'Gio'] as const;

/** Taille lisible, sans dépendance : la même échelle que celle déjà utilisée dans le composeur. */
function tailleLisible(octets: number): string {
  let valeur = octets;
  let unite = 0;
  while (valeur >= 1024 && unite < UNITES.length - 1) {
    valeur /= 1024;
    unite += 1;
  }
  const precision = unite === 0 ? 0 : 1;
  return `${valeur.toFixed(precision)} ${UNITES[unite]}`;
}

export interface CarteArtefactProps {
  artefact: ArtefactPresente;
}

/**
 * Carte cliquable d'un fichier présenté par le modèle (plan d'exécution, lot L3) — visible
 * directement dans le fil, pas repliée comme un appel d'outil ordinaire : c'est tout l'objet de
 * l'outil `presenter_fichier`, faire voir un fichier plutôt que le laisser dans un bloc replié.
 */
export function CarteArtefact({ artefact }: CarteArtefactProps): ReactElement {
  const [ouvert, setOuvert] = useState<boolean>(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOuvert(true)}
        data-testid="carte-artefact"
        className={cn(
          'flex w-full max-w-sm items-center gap-2.5 rounded-md border border-border bg-surface px-3 py-2',
          'text-left transition-colors duration-fast hover:border-border-strong hover:bg-surface-2',
        )}
      >
        <span className="text-text-3">
          <IconeFichier />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm text-text">{artefact.nom_affiche}</span>
          <span className="block text-2xs text-text-3">{tailleLisible(artefact.taille_octets)}</span>
        </span>
      </button>
      <ModaleArtefact artefact={artefact} ouvert={ouvert} onFermer={() => setOuvert(false)} />
    </>
  );
}
