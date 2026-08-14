import { AnimatePresence, motion } from 'framer-motion';
import { useState, type ChangeEvent, type ReactElement } from 'react';
import { Button, Progress, fadeUp } from '../../shared/design';
import type { EtapeInstallation, EvenementInstallation, NiveauEvenement } from '../api/types';
import type { EtatInstallation } from './useInstallationVllm';

/*
 * Installation d'une version vLLM : formulaire, progression réelle, journal, annulation.
 *
 * La version est saisie parce que le backend ne liste que les versions DÉJÀ installées : proposer
 * une liste de versions disponibles supposerait d'interroger PyPI, ce que personne ne fait ici. Un
 * champ libre est moins joli qu'un menu déroulant, mais il ne prétend pas savoir ce qu'il ignore.
 */

const LIBELLE_ETAPE: Record<EtapeInstallation, string> = {
  preparation: 'préparation',
  creation_venv: 'création du venv',
  mise_a_jour_pip: 'mise à jour de pip',
  installation_vllm: 'installation de vLLM',
  alignement_transformers: 'alignement de transformers',
  validation: 'validation par sonde',
  finalisation: 'finalisation',
  annulation: 'annulation',
  echec: 'échec',
};

const COULEUR_NIVEAU: Record<NiveauEvenement, string> = {
  info: 'text-text-2',
  avertissement: 'text-caution',
  erreur: 'text-critical',
  succes: 'text-ok',
};

function Journal({ evenements }: { evenements: EvenementInstallation[] }): ReactElement | null {
  if (evenements.length === 0) {
    return null;
  }
  return (
    <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto rounded-xs bg-bg p-2">
      {evenements.map((evenement) => (
        <li key={`${evenement.horodatage}-${evenement.etape}`} className="flex gap-2 text-2xs">
          <span className="shrink-0 font-mono tabular-nums text-text-3">{LIBELLE_ETAPE[evenement.etape]}</span>
          <span className={COULEUR_NIVEAU[evenement.niveau]}>{evenement.message}</span>
        </li>
      ))}
    </ul>
  );
}

function Avancement({ evenements }: { evenements: EvenementInstallation[] }): ReactElement | null {
  const dernier = evenements[evenements.length - 1];
  if (dernier === undefined) {
    return null;
  }
  return (
    <Progress
      className="mt-3"
      value={dernier.progression}
      max={1}
      tone="accent"
      label="Étapes franchies"
      // La valeur affichée est le nom de l'étape atteinte : une fraction d'étapes ne se lit pas
      // en pourcentage, et le backend n'estime aucune durée.
      format={(): string => LIBELLE_ETAPE[dernier.etape]}
    />
  );
}

const CHAMP_VERSION =
  'h-8 w-full rounded-sm border border-border bg-surface-2 px-2.5 font-mono text-sm tabular-nums ' +
  'text-text outline-none focus-visible:shadow-[0_0_0_3px_var(--ring)] disabled:opacity-45';

function Formulaire({ installation }: { installation: EtatInstallation }): ReactElement {
  const [version, setVersion] = useState<string>('');
  const enCours = installation.phase === 'en_cours';
  const saisie = version.trim();
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="grow">
        <span className="mb-1 block text-xs text-text-2">Version vLLM à installer</span>
        <input
          value={version}
          disabled={enCours}
          placeholder="0.21.0"
          onChange={(evenement: ChangeEvent<HTMLInputElement>): void => setVersion(evenement.target.value)}
          className={CHAMP_VERSION}
        />
      </label>
      {enCours ? (
        <Button variant="danger" onClick={installation.annuler}>
          Annuler
        </Button>
      ) : (
        <Button variant="primary" disabled={saisie === ''} onClick={(): void => installation.demarrer(saisie, false)}>
          Installer
        </Button>
      )}
    </div>
  );
}

export interface InstallationVllmProps {
  installation: EtatInstallation;
}

export function InstallationVllm({ installation }: InstallationVllmProps): ReactElement {
  return (
    <div className="mt-4 border-t border-border pt-4">
      <Formulaire installation={installation} />

      <p className="mt-2 text-2xs text-text-3">
        Chaque version vit dans son propre venv : torch et CUDA de vLLM entrent en conflit avec le reste du backend.
      </p>

      <AnimatePresence>
        {installation.phase !== 'inactive' && (
          <motion.div variants={fadeUp} initial="hidden" animate="visible" exit="exit">
            <Avancement evenements={installation.evenements} />
            <Journal evenements={installation.evenements} />
            {installation.erreur !== null && (
              <p className="mt-2 rounded-xs bg-critical-soft px-2 py-1.5 text-2xs text-critical">
                {installation.erreur}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
