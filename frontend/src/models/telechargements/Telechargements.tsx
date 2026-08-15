import { AnimatePresence, motion } from 'framer-motion';
import type { ReactElement } from 'react';
import { Badge, Button, Card, Progress, fadeUp, type Tone } from '../../shared/design';
import type { EtatTelechargement, Telechargement } from '../api/types';
import { enGo, octetsLisibles } from '../format';
import { estActif, type EtatTelechargements } from './useTelechargements';

/*
 * Téléchargements en cours et passés.
 *
 * Un transfert sans total annoncé n'affiche pas de barre : le Hub ne publie pas toujours la taille
 * de ses fichiers, et une barre sans dénominateur ne serait qu'une animation. On montre alors les
 * octets réellement écrits, qui restent une mesure.
 *
 * Annuler ne supprime rien par défaut : les octets déjà sur le disque servent à la reprise. La
 * suppression est une seconde action, explicite.
 */

const LIBELLE_ETAT: Record<EtatTelechargement, string> = {
  en_attente: 'en attente',
  en_cours: 'en cours',
  termine: 'terminé',
  annule: 'annulé',
  interrompu: 'interrompu',
  erreur: 'erreur',
};

const TON_ETAT: Record<EtatTelechargement, Tone> = {
  en_attente: 'neutral',
  en_cours: 'accent',
  termine: 'ok',
  annule: 'neutral',
  interrompu: 'caution',
  erreur: 'critical',
};

function Avancement({ telechargement }: { telechargement: Telechargement }): ReactElement {
  if (telechargement.octets_totaux === null) {
    return (
      <p className="mt-2 font-mono text-2xs tabular-nums text-text-2">
        {octetsLisibles(telechargement.octets_recus)} écrits — taille totale non annoncée par le Hub.
      </p>
    );
  }
  return (
    <Progress
      className="mt-2"
      value={telechargement.octets_recus}
      max={telechargement.octets_totaux}
      tone={TON_ETAT[telechargement.etat]}
      format={(recus, total): string => `${enGo(recus)} / ${enGo(total)} Go`}
    />
  );
}

function Actions({
  telechargement,
  actions,
}: {
  telechargement: Telechargement;
  actions: EtatTelechargements;
}): ReactElement {
  if (estActif(telechargement)) {
    return (
      <Button size="sm" variant="danger" onClick={(): void => actions.annuler(telechargement.identifiant, false)}>
        Annuler
      </Button>
    );
  }
  if (telechargement.etat === 'termine') {
    return <span className="text-2xs text-text-3">{octetsLisibles(telechargement.octets_recus)}</span>;
  }
  return (
    <div className="flex gap-1.5">
      <Button size="sm" variant="secondary" onClick={(): void => actions.relancer(telechargement.identifiant)}>
        Reprendre
      </Button>
      <Button size="sm" variant="ghost" onClick={(): void => actions.annuler(telechargement.identifiant, true)}>
        Supprimer
      </Button>
    </div>
  );
}

function Ligne({
  telechargement,
  actions,
}: {
  telechargement: Telechargement;
  actions: EtatTelechargements;
}): ReactElement {
  return (
    <Card level="raised" padding="sm">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between lg:gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text">{telechargement.depot}</p>
          <p className="truncate font-mono text-2xs tabular-nums text-text-3">
            {telechargement.fichier ?? 'dépôt entier'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:shrink-0 lg:flex-nowrap">
          <Badge tone={TON_ETAT[telechargement.etat]} dot pulse={estActif(telechargement)}>
            {LIBELLE_ETAT[telechargement.etat]}
          </Badge>
          <Actions telechargement={telechargement} actions={actions} />
        </div>
      </div>
      <Avancement telechargement={telechargement} />
      {telechargement.erreur !== null && (
        <p className="mt-2 rounded-xs bg-critical-soft px-2 py-1.5 text-2xs text-critical">
          {telechargement.erreur}
          {telechargement.remediation !== null && (
            <span className="mt-1 block text-caution">{telechargement.remediation}</span>
          )}
        </p>
      )}
    </Card>
  );
}

export function Telechargements({ etat }: { etat: EtatTelechargements }): ReactElement {
  if (etat.liste.length === 0) {
    return (
      <p className="text-xs text-text-2">
        {etat.chargement ? 'Lecture du journal des transferts…' : 'Aucun téléchargement enregistré.'}
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {etat.erreur !== null && <p className="text-2xs text-caution">{etat.erreur}</p>}
      <AnimatePresence initial={false}>
        {etat.liste.map((telechargement) => (
          <motion.div
            key={telechargement.identifiant}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            exit="exit"
            layout
          >
            <Ligne telechargement={telechargement} actions={etat} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
