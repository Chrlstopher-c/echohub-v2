import { AnimatePresence, motion } from 'framer-motion';
import type { ReactElement, ReactNode } from 'react';
import { Badge, Button, Card, fadeUp } from '../../shared/design';
import type { ModeleEnregistre } from '../api/types';
import { PastilleFaisabilite } from '../faisabilite/Faisabilite';
import { evaluer, type BudgetMemoire } from '../faisabilite/evaluation';
import { entier, octetsLisibles } from '../format';
import type { EtatModelesLocaux } from './useModelesLocaux';

/*
 * Modèles présents sur le disque.
 *
 * Un champ vide veut dire « pas encore mesuré », jamais « estimé » : `nb_couches` absent signifie
 * que l'en-tête n'a pas été lu, et l'interface le dit avec ces mots-là. C'est cette distinction que
 * la v1 perdait en recopiant des estimations en base, ensuite traitées comme des faits.
 */

function Champ({ libelle, children }: { libelle: string; children: ReactNode }): ReactElement {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-2xs text-text-3">{libelle}</dt>
      <dd className="min-w-0 truncate text-right font-mono text-2xs tabular-nums text-text-2">{children}</dd>
    </div>
  );
}

function EtatMetadonnees({ modele }: { modele: ModeleEnregistre }): ReactElement {
  if (modele.nb_couches === null) {
    return <Badge tone="caution">métadonnées non lues</Badge>;
  }
  return <Badge tone="ok">{`${entier(modele.nb_couches)} couches lues`}</Badge>;
}

function EnTeteModele({ modele, budget }: { modele: ModeleEnregistre; budget: BudgetMemoire }): ReactElement {
  return (
    <div className="mb-2 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="truncate text-md font-semibold text-text">{modele.fichier ?? modele.depot}</h3>
        <p className="truncate text-2xs text-text-3">{modele.depot}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Badge tone="neutral">{modele.format}</Badge>
        <PastilleFaisabilite faisabilite={evaluer(modele.taille_octets, budget)} />
      </div>
    </div>
  );
}

function ActionsModele({
  modele,
  onCharger,
  onOublier,
}: {
  modele: ModeleEnregistre;
  onCharger?: (modele: ModeleEnregistre) => void;
  onOublier: (identifiant: string) => void;
}): ReactElement {
  return (
    <div className="mt-3 flex items-center justify-between gap-2">
      <EtatMetadonnees modele={modele} />
      <div className="flex gap-1.5">
        <Button size="sm" variant="ghost" onClick={(): void => onOublier(modele.id)}>
          Oublier
        </Button>
        {onCharger !== undefined && (
          <Button size="sm" variant="primary" onClick={(): void => onCharger(modele)}>
            Charger
          </Button>
        )}
      </div>
    </div>
  );
}

function CarteModele({
  modele,
  budget,
  onCharger,
  onOublier,
}: {
  modele: ModeleEnregistre;
  budget: BudgetMemoire;
  onCharger?: (modele: ModeleEnregistre) => void;
  onOublier: (identifiant: string) => void;
}): ReactElement {
  return (
    <Card level="surface">
      <EnTeteModele modele={modele} budget={budget} />
      <dl className="space-y-1">
        <Champ libelle="Taille sur disque">{octetsLisibles(modele.taille_octets)}</Champ>
        <Champ libelle="Quantification">{modele.quantification ?? 'non lue'}</Champ>
        <Champ libelle="Architecture">{modele.architecture ?? 'non lue'}</Champ>
        <Champ libelle="Contexte natif">
          {modele.contexte_max === null ? 'non lu' : `${entier(modele.contexte_max)} tokens`}
        </Champ>
      </dl>
      <ActionsModele modele={modele} onCharger={onCharger} onOublier={onOublier} />
    </Card>
  );
}

export interface ModelesLocauxProps {
  etat: EtatModelesLocaux;
  budget: BudgetMemoire;
  /**
   * Le chargement appartient au domaine `inference` : cet écran délègue et ne construit aucun plan.
   * Absent, le bouton n'apparaît pas — mieux vaut pas d'action qu'une action qui ne mène nulle part.
   */
  onCharger?: (modele: ModeleEnregistre) => void;
}

export function ModelesLocaux({ etat, budget, onCharger }: ModelesLocauxProps): ReactElement {
  if (etat.liste.length === 0) {
    return (
      <p className="text-xs text-text-2">
        {etat.chargement ? 'Lecture du registre…' : 'Aucun modèle sur le disque. La recherche est à côté.'}
      </p>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <AnimatePresence initial={false}>
        {etat.liste.map((modele) => (
          <motion.div key={modele.id} variants={fadeUp} initial="hidden" animate="visible" exit="exit" layout>
            <CarteModele modele={modele} budget={budget} onCharger={onCharger} onOublier={etat.oublier} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
