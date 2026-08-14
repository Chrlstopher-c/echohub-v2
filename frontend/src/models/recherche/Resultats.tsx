import { AnimatePresence, motion } from 'framer-motion';
import type { ReactElement } from 'react';
import { Badge, Button, Card, fadeUp } from '../../shared/design';
import type { Capacite, ResultatRecherche } from '../api/types';
import { PastilleFaisabilite } from '../faisabilite/Faisabilite';
import type { BudgetMemoire, Verdict } from '../faisabilite/evaluation';
import { miseEnAvant, repartition, variantes, type Variante } from '../faisabilite/variantes';
import { compact, dateCourte, octetsLisibles } from '../format';
import { CapacitesDeduites } from './CapacitesDeduites';
import type { CarteCapacites } from './capacites';

/*
 * Résultats de recherche : un dépôt par carte, lisible d'un coup d'œil.
 *
 * La hiérarchie de lecture est délibérée — nom, puis faisabilité, puis popularité. Un modèle très
 * téléchargé qui ne rentre pas dans 16 Go n'a aucun intérêt sur cette machine, et l'interface doit
 * le dire avant que l'utilisateur ne lance vingt gigaoctets de transfert.
 *
 * Les capacités déduites s'insèrent après le verdict et avant les compteurs : elles disent ce que
 * le dépôt prétend savoir faire, ce qui n'a d'intérêt qu'une fois su que le modèle tient sur la
 * machine. Elles ne montent donc pas dans l'en-tête, où elles concurrenceraient une mesure.
 */

const TON_VARIANTE: Record<Verdict, 'vram' | 'ram' | 'critical' | 'neutral'> = {
  tient_vram: 'vram',
  deborde_ram: 'ram',
  ne_tient_pas: 'critical',
  indeterminee: 'neutral',
};

/** Au-delà, la ligne de variantes cesse d'être lisible d'un coup d'œil ; le reste est compté. */
const VARIANTES_VISIBLES = 6;

function Variantes({ liste }: { liste: readonly Variante[] }): ReactElement {
  const visibles = liste.slice(0, VARIANTES_VISIBLES);
  const restantes = liste.length - visibles.length;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {visibles.map((variante) => (
        <Badge key={variante.fichier ?? 'dossier'} tone={TON_VARIANTE[variante.faisabilite.verdict]}>
          <span className="font-mono tabular-nums">
            {variante.etiquette ?? variante.fichier ?? 'dépôt'} · {octetsLisibles(variante.tailleOctets)}
          </span>
        </Badge>
      ))}
      {restantes > 0 && <span className="text-2xs text-text-3">+{restantes}</span>}
    </div>
  );
}

function Statistiques({ resultat }: { resultat: ResultatRecherche }): ReactElement {
  return (
    <p className="font-mono text-2xs tabular-nums text-text-3">
      {`${compact(resultat.telechargements)} téléchargements · ${compact(resultat.mentions)} mentions · `}
      {`modifié le ${dateCourte(resultat.modifie_le)}`}
    </p>
  );
}

function Resume({ liste }: { liste: readonly Variante[] }): ReactElement | null {
  const compte = repartition(liste);
  if (liste.length <= 1) {
    return null;
  }
  return (
    <p className="text-2xs text-text-2">
      <span className="text-mem-vram">{compte.tientVram} en VRAM</span>
      {' · '}
      <span className="text-mem-ram">{compte.debordeRam} avec couches en RAM</span>
      {' · '}
      <span className="text-critical">{compte.neTientPas} hors budget</span>
    </p>
  );
}

function EnTeteDepot({ resultat, avant }: { resultat: ResultatRecherche; avant: Variante | null }): ReactElement {
  return (
    <div className="mb-2 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="truncate text-md font-semibold text-text">{resultat.nom}</h3>
        <p className="truncate text-2xs text-text-3">{resultat.auteur ?? resultat.depot}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {resultat.gated && <Badge tone="caution">accès restreint</Badge>}
        {resultat.deja_telecharge && <Badge tone="ok">sur le disque</Badge>}
        {avant !== null && <PastilleFaisabilite faisabilite={avant.faisabilite} />}
      </div>
    </div>
  );
}

function CarteDepot({
  resultat,
  budget,
  vocabulaire,
  exigees,
  onChoisir,
}: {
  resultat: ResultatRecherche;
  budget: BudgetMemoire;
  vocabulaire: CarteCapacites;
  exigees: readonly Capacite[];
  onChoisir: (resultat: ResultatRecherche) => void;
}): ReactElement {
  const liste = variantes(resultat, budget);
  return (
    <Card level="surface">
      <EnTeteDepot resultat={resultat} avant={miseEnAvant(liste)} />
      <div className="space-y-2">
        <Variantes liste={liste} />
        <Resume liste={liste} />
        <CapacitesDeduites deduites={resultat.capacites_deduites} carte={vocabulaire} exigees={exigees} />
        <Statistiques resultat={resultat} />
      </div>

      <div className="mt-3 flex justify-end">
        <Button size="sm" variant="secondary" onClick={(): void => onChoisir(resultat)}>
          Télécharger…
        </Button>
      </div>
    </Card>
  );
}

export interface ResultatsProps {
  resultats: readonly ResultatRecherche[];
  budget: BudgetMemoire;
  /** Libellés publiés des capacités ; vide tant que le vocabulaire n'a pas été lu. */
  vocabulaire: CarteCapacites;
  /** Capacités actuellement filtrées — signalées sur les cartes pour relier filtre et résultat. */
  exigees: readonly Capacite[];
  onChoisir: (resultat: ResultatRecherche) => void;
}

export function Resultats({ resultats, budget, vocabulaire, exigees, onChoisir }: ResultatsProps): ReactElement {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <AnimatePresence initial={false}>
        {resultats.map((resultat) => (
          <motion.div key={resultat.depot} variants={fadeUp} initial="hidden" animate="visible" exit="exit" layout>
            <CarteDepot
              resultat={resultat}
              budget={budget}
              vocabulaire={vocabulaire}
              exigees={exigees}
              onChoisir={onChoisir}
            />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
