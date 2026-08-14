import type { ReactElement } from 'react';
import { Button, Card } from '../../shared/design';
import type { ResultatRecherche } from '../api/types';
import { BandeauReserve } from '../faisabilite/Faisabilite';
import type { BudgetMemoire } from '../faisabilite/evaluation';
import { BarreRecherche } from './BarreRecherche';
import { Resultats } from './Resultats';
import type { EtatRecherche } from './useRecherche';

/* Onglet « Découvrir » : saisie, résultats, pagination, et la réserve qui encadre les verdicts. */

function Pagination({ recherche }: { recherche: EtatRecherche }): ReactElement {
  const page = recherche.critere.page;
  return (
    <div className="flex shrink-0 gap-1.5">
      <Button
        size="sm"
        disabled={page === 0 || recherche.chargement}
        onClick={(): void => recherche.allerPage(page - 1)}
      >
        Précédent
      </Button>
      <Button
        size="sm"
        disabled={(recherche.page?.fin_atteinte ?? true) || recherche.chargement}
        onClick={(): void => recherche.allerPage(page + 1)}
      >
        Suivant
      </Button>
    </div>
  );
}

export interface PanneauDecouverteProps {
  recherche: EtatRecherche;
  budget: BudgetMemoire;
  onChoisir: (resultat: ResultatRecherche) => void;
}

export function PanneauDecouverte({ recherche, budget, onChoisir }: PanneauDecouverteProps): ReactElement {
  return (
    <div className="space-y-4">
      <Card padding="sm">
        <BarreRecherche recherche={recherche} />
      </Card>
      {recherche.erreur !== null && (
        <p className="rounded-xs bg-critical-soft px-2 py-1.5 text-2xs text-critical">{recherche.erreur}</p>
      )}
      <Resultats resultats={recherche.page?.resultats ?? []} budget={budget} onChoisir={onChoisir} />
      <div className="flex items-start justify-between gap-4">
        <BandeauReserve />
        <Pagination recherche={recherche} />
      </div>
    </div>
  );
}
