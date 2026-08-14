import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { Badge, Button, Card } from '../../shared/design';
import { journal } from '../api/client';
import { supprimerVersionVllm, type OptionsEtat } from '../api/moteurs';
import type { EtatMoteurs, VersionVllm } from '../api/types';
import { octetsLisibles } from '../format';
import { CarteMoteur } from './CarteMoteur';
import { InstallationVllm } from './InstallationVllm';
import { useInstallationVllm } from './useInstallationVllm';
import { useMoteurs } from './useMoteurs';

/*
 * Section « Moteurs » de l'écran Système : santé de llama.cpp et de vLLM, venvs installés,
 * installation d'une version. Les deux moteurs ne cohabitent jamais sur le GPU — vLLM prééalloue
 * sa VRAM et ne la rend qu'à l'arrêt — mais cette exclusivité est arbitrée par le planificateur,
 * pas ici : cet écran décrit ce qui est installé, pas ce qui tourne.
 */

type Recharger = (options?: OptionsEtat) => void;

function LigneVersion({
  version,
  onSupprimer,
  suppressionEnCours,
}: {
  version: VersionVllm;
  onSupprimer: (version: string) => void;
  suppressionEnCours: boolean;
}): ReactElement {
  return (
    <li className="flex items-center justify-between gap-3 border-t border-border py-2 first:border-t-0">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs tabular-nums text-text">{version.version}</span>
          <Badge tone={version.utilisable ? 'ok' : 'caution'}>{version.utilisable ? 'validé' : version.statut}</Badge>
        </div>
        <p className="truncate text-2xs text-text-3">
          {`torch ${version.version_torch ?? '—'} · transformers ${version.version_transformers ?? '—'} · `}
          {octetsLisibles(version.taille_octets)}
        </p>
      </div>
      <Button
        size="sm"
        variant="danger"
        loading={suppressionEnCours}
        onClick={(): void => onSupprimer(version.version)}
      >
        Supprimer
      </Button>
    </li>
  );
}

function ListeVersions({
  versions,
  onSupprimer,
  suppression,
}: {
  versions: VersionVllm[];
  onSupprimer: (version: string) => void;
  suppression: string | null;
}): ReactElement {
  if (versions.length === 0) {
    return <p className="text-xs text-text-2">Aucun venv vLLM sur le disque.</p>;
  }
  return (
    <ul>
      {versions.map((version) => (
        <LigneVersion
          key={version.version}
          version={version}
          onSupprimer={onSupprimer}
          suppressionEnCours={suppression === version.version}
        />
      ))}
    </ul>
  );
}

/** Suppression d'un venv, avec le venv en cours de suppression pour l'état du bouton. */
function useSuppression(recharger: Recharger): { enCours: string | null; supprimer: (version: string) => void } {
  const [enCours, setEnCours] = useState<string | null>(null);
  const supprimer = useCallback(
    (version: string): void => {
      setEnCours(version);
      supprimerVersionVllm(version)
        .then(() => recharger({ verifierVllm: false }))
        .catch((cause: unknown) => journal.erreur(`suppression du venv vLLM ${version}`, cause))
        .finally(() => setEnCours(null));
    },
    [recharger],
  );
  return { enCours, supprimer };
}

interface CarteVllmProps {
  etat: EtatMoteurs;
  recharger: Recharger;
  chargement: boolean;
}

function CarteVllm({ etat, recharger, chargement }: CarteVllmProps): ReactElement {
  const installation = useInstallationVllm();
  const suppression = useSuppression(recharger);

  // Une installation qui aboutit change l'état du disque : la mesure affichée doit être refaite.
  useEffect(() => {
    if (installation.phase === 'terminee') {
      recharger({ verifierVllm: true });
    }
  }, [installation.phase, recharger]);

  return (
    <CarteMoteur
      titre="vLLM"
      sante={etat.vllm}
      sondage={chargement}
      onSonder={(): void => recharger({ verifierVllm: true })}
    >
      <div className="mt-4 border-t border-border pt-3">
        <h3 className="mb-2 text-xs text-text-2">Versions installées</h3>
        <ListeVersions
          versions={etat.versions_vllm}
          onSupprimer={suppression.supprimer}
          suppression={suppression.enCours}
        />
      </div>
      <InstallationVllm installation={installation} />
    </CarteMoteur>
  );
}

export function Moteurs(): ReactElement {
  const { etat, erreur, chargement, recharger } = useMoteurs();

  if (etat === null) {
    return (
      <Card title="Moteurs">
        <p className="text-xs text-text-2">{erreur ?? 'Lecture de l’état des moteurs…'}</p>
        {erreur !== null && (
          <Button className="mt-3" size="sm" onClick={(): void => recharger()}>
            Réessayer
          </Button>
        )}
      </Card>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <CarteMoteur
        titre="llama.cpp"
        sante={etat.llamacpp}
        sondage={chargement}
        onSonder={(): void => recharger({ forcerLlamacpp: true })}
      />
      <CarteVllm etat={etat} recharger={recharger} chargement={chargement} />
    </div>
  );
}
