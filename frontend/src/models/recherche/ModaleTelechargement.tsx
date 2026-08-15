import { useEffect, useState, type ReactElement } from 'react';
import { Button, Modal, cn } from '../../shared/design';
import { messageErreur } from '../api/client';
import { detailsDepot } from '../api/recherche';
import { demarrerTelechargement } from '../api/telechargements';
import type { ResultatRecherche } from '../api/types';
import { PastilleFaisabilite } from '../faisabilite/Faisabilite';
import { RESERVE, type BudgetMemoire } from '../faisabilite/evaluation';
import { variantes, type Variante } from '../faisabilite/variantes';
import { octetsLisibles } from '../format';

/*
 * Choix de la quantification à télécharger.
 *
 * La fiche complète du dépôt est redemandée à l'ouverture : la liste de recherche n'expose pas
 * toujours la taille de chaque fichier, et choisir une variante sans connaître son poids serait
 * choisir à l'aveugle — exactement ce que cet écran doit rendre impossible.
 */

function LigneVariante({
  variante,
  choisie,
  onChoisir,
}: {
  variante: Variante;
  choisie: boolean;
  onChoisir: () => void;
}): ReactElement {
  return (
    <li>
      <button
        type="button"
        onClick={onChoisir}
        aria-pressed={choisie}
        className={cn(
          'flex min-h-[44px] w-full items-center justify-between gap-3 rounded-sm border px-2.5 py-2 text-left',
          'lg:min-h-0',
          'transition-colors duration-fast ease-out',
          choisie ? 'border-accent bg-accent-soft' : 'border-border bg-surface-2 hover:border-border-strong',
        )}
      >
        <span className="min-w-0">
          <span className="block truncate font-mono text-xs tabular-nums text-text">
            {variante.etiquette ?? variante.fichier ?? 'dépôt entier'}
          </span>
          <span className="block truncate text-2xs text-text-3">{variante.fichier ?? 'tous les fichiers'}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-xs tabular-nums text-text-2">{octetsLisibles(variante.tailleOctets)}</span>
          <PastilleFaisabilite faisabilite={variante.faisabilite} compacte />
        </span>
      </button>
    </li>
  );
}

function useFiche(depot: ResultatRecherche | null): { fiche: ResultatRecherche | null; erreur: string | null } {
  const [fiche, setFiche] = useState<ResultatRecherche | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    if (depot === null) {
      return undefined;
    }
    const controleur = new AbortController();
    setFiche(depot);
    setErreur(null);
    detailsDepot(depot.depot, controleur.signal)
      .then(setFiche)
      .catch((cause: unknown) => {
        if (!controleur.signal.aborted) {
          setErreur(messageErreur(cause));
        }
      });
    return (): void => controleur.abort();
  }, [depot]);

  return { fiche, erreur };
}

interface Lancement {
  lancer: () => void;
  envoi: boolean;
  echec: string | null;
}

function useLancement(
  fiche: ResultatRecherche | null,
  selection: Variante | undefined,
  surLance: () => void,
  surFerme: () => void,
): Lancement {
  const [envoi, setEnvoi] = useState<boolean>(false);
  const [echec, setEchec] = useState<string | null>(null);

  const lancer = (): void => {
    if (fiche === null || selection === undefined) {
      return;
    }
    setEnvoi(true);
    setEchec(null);
    demarrerTelechargement({ depot: fiche.depot, fichier: selection.fichier })
      .then(() => {
        surLance();
        surFerme();
      })
      .catch((cause: unknown) => setEchec(messageErreur(cause)))
      .finally(() => setEnvoi(false));
  };

  return { lancer, envoi, echec };
}

function PiedModale({ lancement, actif, onFermer }: {
  lancement: Lancement;
  actif: boolean;
  onFermer: () => void;
}): ReactElement {
  return (
    <>
      <Button variant="ghost" onClick={onFermer}>
        Annuler
      </Button>
      <Button variant="primary" loading={lancement.envoi} disabled={!actif} onClick={lancement.lancer}>
        Télécharger
      </Button>
    </>
  );
}

export interface ModaleTelechargementProps {
  depot: ResultatRecherche | null;
  budget: BudgetMemoire;
  onFermer: () => void;
  /** Le transfert est déjà connu du backend : l'appelant relit la liste, il n'en insère aucun état. */
  onLance: () => void;
}

export function ModaleTelechargement({ depot, budget, onFermer, onLance }: ModaleTelechargementProps): ReactElement {
  const { fiche, erreur } = useFiche(depot);
  const [choisi, setChoisi] = useState<string | null>(null);
  const liste: Variante[] = fiche === null ? [] : variantes(fiche, budget);
  const selection = liste.find((variante) => (variante.fichier ?? '') === (choisi ?? '')) ?? liste[0];
  const lancement = useLancement(fiche, selection, onLance, onFermer);

  return (
    <Modal
      open={depot !== null}
      onClose={onFermer}
      title={fiche?.depot ?? 'Téléchargement'}
      footer={<PiedModale lancement={lancement} actif={selection !== undefined} onFermer={onFermer} />}
    >
      {erreur !== null && <p className="mb-3 text-xs text-critical">{erreur}</p>}
      {lancement.echec !== null && <p className="mb-3 text-xs text-critical">{lancement.echec}</p>}
      {/* Sous le seuil, la modale est déjà plein écran et son corps défile : une seconde borne de
          hauteur y créerait un défilement dans le défilement. Le plafond reste un geste de bureau. */}
      <ul className="space-y-1.5 lg:max-h-72 lg:overflow-y-auto">
        {liste.map((variante) => (
          <LigneVariante
            key={variante.fichier ?? 'dossier'}
            variante={variante}
            choisie={selection === variante}
            onChoisir={(): void => setChoisi(variante.fichier)}
          />
        ))}
      </ul>
      <p className="mt-3 text-2xs leading-relaxed text-text-3">{RESERVE}</p>
    </Modal>
  );
}
