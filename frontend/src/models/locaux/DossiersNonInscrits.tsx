/*
 * Dossiers présents sur le disque que le registre a refusés.
 *
 * Ils existent parce que le refus est justifié — un fichier auxiliaire ou un téléchargement
 * inachevé ne doit pas être proposé au chargement — mais les taire les rendait invisibles ET
 * indestructibles depuis l'interface : plus de douze gigaoctets occupés sans aucun moyen d'agir.
 *
 * La présentation est délibérément sobre et distincte des modèles utilisables : ce n'est pas une
 * bibliothèque, c'est un reste à traiter. Chaque ligne porte sa cause et ce qu'il faut en faire.
 */

import { useState } from 'react';
import type { ReactElement } from 'react';

import {
  Badge,
  BoutonActions,
  Button,
  MenuContextuel,
  cn,
  type ApiMenuContextuel,
  type EntreeMenu,
} from '../../shared/design';
import { octetsLisibles } from '../format';
import type { DossierDisque } from '../api/types';

interface LigneProps {
  readonly dossier: DossierDisque;
  readonly onSupprimer: () => void;
}

function Ligne({ dossier, onSupprimer }: LigneProps): ReactElement {
  const [confirme, setConfirme] = useState(false);

  const entrees: EntreeMenu[] = [
    { libelle: 'Copier le nom', onChoisir: () => void navigator.clipboard?.writeText(dossier.dossier) },
    { libelle: 'Supprimer du disque', onChoisir: () => setConfirme(true), destructive: true },
  ];

  return (
    <MenuContextuel entrees={entrees} className="block">
      {({ ouvrirDepuis }: ApiMenuContextuel): ReactElement => (
      <li
        className={cn(
          'flex flex-col gap-2 rounded-md border border-border px-3 py-2.5',
          'lg:flex-row lg:items-start lg:justify-between lg:gap-4',
        )}
      >
        <div className="min-w-0">
          <p className="truncate font-mono text-xs text-text-2">{dossier.dossier}</p>
          <p className="mt-0.5 text-2xs leading-relaxed text-text-3">{dossier.raison}</p>
          {dossier.remediation !== '' && (
            <p className="mt-0.5 text-2xs leading-relaxed text-text-3">{dossier.remediation}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:shrink-0 lg:flex-nowrap">
          <span className="font-mono text-xs tabular-nums text-text-2">
            {octetsLisibles(dossier.taille_octets)}
          </span>
          {/* « Copier le nom » n'existe que dans le menu : sans ce bouton, l'action serait
              inatteignable au doigt, faute de clic droit. */}
          <BoutonActions
            libelle="Actions sur le dossier"
            className="lg:hidden"
            onClick={(evenement): void => ouvrirDepuis(evenement.currentTarget)}
          />
          {confirme ? (
            <>
              <Button variant="ghost" size="sm" onClick={() => setConfirme(false)}>
                Annuler
              </Button>
              {/* La confirmation est explicite : la suppression est irréversible et porte sur
                  plusieurs gigaoctets. Un seul clic serait trop peu. */}
              <Button variant="secondary" size="sm" onClick={onSupprimer}>
                Confirmer
              </Button>
            </>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setConfirme(true)}>
              Supprimer
            </Button>
          )}
        </div>
      </li>
      )}
    </MenuContextuel>
  );
}

export interface DossiersNonInscritsProps {
  readonly dossiers: readonly DossierDisque[];
  readonly onSupprimer: (dossier: string) => void;
}

export function DossiersNonInscrits({ dossiers, onSupprimer }: DossiersNonInscritsProps): ReactElement | null {
  const refuses = dossiers.filter((dossier) => !dossier.inscrit);
  if (refuses.length === 0) {
    return null;
  }
  const total = refuses.reduce((somme, dossier) => somme + dossier.taille_octets, 0);
  return (
    <section className="mt-8">
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-xs font-medium uppercase tracking-wide text-text-3">Non utilisables</h3>
        <Badge tone="caution">
          {refuses.length} dossier{refuses.length > 1 ? 's' : ''} · {octetsLisibles(total)}
        </Badge>
      </header>
      <p className="mb-3 text-2xs leading-relaxed text-text-3">
        Présents sur le disque mais impossibles à charger. Le registre les écarte à raison ; ils
        occupent de la place tant qu'ils ne sont pas supprimés.
      </p>
      <ul className="space-y-1.5">
        {refuses.map((dossier) => (
          <Ligne key={dossier.dossier} dossier={dossier} onSupprimer={() => onSupprimer(dossier.dossier)} />
        ))}
      </ul>
    </section>
  );
}
