import type { ReactElement } from 'react';
import { Button, Card } from '../../shared/design';
import type { ResultatRecherche } from '../api/types';
import { BandeauReserve } from '../faisabilite/Faisabilite';
import type { BudgetMemoire } from '../faisabilite/evaluation';
import { BarreRecherche } from './BarreRecherche';
import { Resultats } from './Resultats';
import { useDefinitionsCapacites } from './useDefinitionsCapacites';
import type { EtatRecherche } from './useRecherche';

/*
 * Onglet « Découvrir » : saisie, résultats, pagination, et la réserve qui encadre les verdicts.
 *
 * Le vocabulaire des capacités est chargé ici, au montage de l'onglet, puis partagé entre les
 * filtres et les cartes : les deux doivent nommer une capacité exactement pareil, ce qui n'est
 * garanti que s'ils lisent la même réponse. Quitter puis revenir sur l'onglet relit la liste — un
 * GET sans paramètre, préférable à un cache dont personne ne saurait dire quand il est périmé.
 */

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
  const vocabulaire = useDefinitionsCapacites();
  return (
    <div className="space-y-4">
      <Card padding="sm">
        <BarreRecherche recherche={recherche} vocabulaire={vocabulaire} />
      </Card>
      {recherche.erreur !== null && (
        <p className="rounded-xs bg-critical-soft px-2 py-1.5 text-2xs text-critical">{recherche.erreur}</p>
      )}
      <Resultats
        resultats={recherche.page?.resultats ?? []}
        budget={budget}
        vocabulaire={vocabulaire.carte}
        exigees={recherche.critere.capacites}
        onChoisir={onChoisir}
      />
      <div className="flex items-start justify-between gap-4">
        <BandeauReserve />
        <Pagination recherche={recherche} />
      </div>
    </div>
  );
}
