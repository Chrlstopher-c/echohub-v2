import { AnimatePresence, motion } from 'framer-motion';
import { useState } from 'react';
import type { ReactElement } from 'react';
import { Badge, Button, Card, fadeUp } from '../../shared/design';
import type { PlanDeChargement } from '../api/contrats';
import { ArbitrageContexte } from './ArbitrageContexte';
import { BarresMemoire } from './BarresMemoire';
import { EtatChargement } from './EtatChargement';
import { Justifications } from './Justifications';
import { RubanCouches } from './RubanCouches';
import type { CibleChargement } from './cible';
import type { EtatChargementModele } from './useChargement';
import type { EtatPlan } from './usePlan';

/*
 * La pièce maîtresse : le plan de chargement rendu lisible AVANT qu'il ne soit appliqué.
 *
 * Ordre de lecture voulu : ce que ça occupe (barres à l'échelle réelle), comment c'est réparti
 * (cellules de couches), ce que coûte le contexte (arbitrage mesuré), puis pourquoi chaque valeur
 * a été retenue (justifications). L'action de charger vient en dernier — après la compréhension.
 */

function EnTete({ cible, etatPlan }: { cible: CibleChargement; etatPlan: EtatPlan }): ReactElement {
  const plan = etatPlan.plan;
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0">
        <p className="truncate text-md font-semibold text-text">{cible.nomModele}</p>
        <p className="truncate text-2xs text-text-3">{cible.demande.profil.nom_gpu}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {plan !== null && <Badge tone="neutral">{plan.moteur.valeur}</Badge>}
        {plan !== null && plan.niveau_degradation > 0 && (
          <Badge tone="caution">replié · niveau {plan.niveau_degradation}</Badge>
        )}
        {etatPlan.calculEnCours && (
          <Badge tone="accent" dot pulse>
            recalcul
          </Badge>
        )}
      </div>
    </div>
  );
}

interface ActionsProps {
  cible: CibleChargement;
  plan: PlanDeChargement;
  chargement: EtatChargementModele;
}

function Actions({ cible, plan, chargement }: ActionsProps): ReactElement {
  const enCours = chargement.statut?.etat === 'en_cours';
  const pret = chargement.statut?.etat === 'pret';
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="primary"
        size="sm"
        loading={enCours}
        onClick={() => void chargement.demarrer(cible.cheminModele, plan)}
      >
        {pret ? 'Recharger avec ce plan' : 'Charger avec ce plan'}
      </Button>
      {chargement.erreur !== null && <span className="text-2xs text-critical">{chargement.erreur}</span>}
    </div>
  );
}

interface CorpsProps {
  cible: CibleChargement;
  plan: PlanDeChargement;
  etatPlan: EtatPlan;
  chargement: EtatChargementModele;
  debitObserve: number | null;
}

function CorpsPlan({ cible, plan, etatPlan, chargement, debitObserve }: CorpsProps): ReactElement {
  const [detailOuvert, setDetailOuvert] = useState<boolean>(false);
  return (
    <>
      <BarresMemoire plan={plan} vramTotaleOctets={cible.demande.profil.vram_totale_octets} />
      <RubanCouches plan={plan} />
      <ArbitrageContexte
        plan={plan}
        contexteDemande={etatPlan.preferences.contexte}
        contexteMaximum={cible.demande.metadonnees.contexte_entrainement_max}
        debitObserve={debitObserve}
        onChangerContexte={(contexte) => etatPlan.ajusterPreferences({ contexte })}
        desactive={chargement.statut?.etat === 'en_cours'}
      />
      <Button variant="ghost" size="sm" onClick={() => setDetailOuvert(!detailOuvert)} aria-expanded={detailOuvert}>
        {detailOuvert ? 'Masquer le détail du plan' : 'Pourquoi ces valeurs ?'}
      </Button>
      <AnimatePresence initial={false}>
        {detailOuvert && (
          <motion.div variants={fadeUp} initial="hidden" animate="visible" exit="exit">
            <Justifications plan={plan} />
          </motion.div>
        )}
      </AnimatePresence>
      <Actions cible={cible} plan={plan} chargement={chargement} />
    </>
  );
}

interface SuiviProps {
  cible: CibleChargement;
  plan: PlanDeChargement | null;
  etatPlan: EtatPlan;
  chargement: EtatChargementModele;
}

/* Le suivi reste monté même sans plan calculé : un échec précédent doit rester lisible. */
function SuiviChargement({ cible, plan, etatPlan, chargement }: SuiviProps): ReactElement {
  const demanderDegradation = (): void => {
    if (plan === null) {
      return;
    }
    void chargement.proposerDegradation(cible.demande, plan);
  };
  return (
    <EtatChargement
      statut={chargement.statut}
      entrees={chargement.entrees}
      debutMs={chargement.debutMs}
      planDegrade={chargement.planDegrade}
      onDemanderDegradation={demanderDegradation}
      onAdopterDegradation={(reponse) => {
        etatPlan.adopterPlan(reponse);
        chargement.oublierDegradation();
      }}
    />
  );
}

function PlanAbsent(): ReactElement {
  return (
    <Card title="Plan de chargement">
      <p className="text-xs leading-relaxed text-text-2">
        Aucun modèle sélectionné. Le plan apparaîtra ici : ce qui tiendra en VRAM, ce qui sera déporté
        en RAM, et ce que coûtera le contexte demandé.
      </p>
    </Card>
  );
}

export interface PanneauPlanProps {
  cible: CibleChargement | null;
  etatPlan: EtatPlan;
  chargement: EtatChargementModele;
  /** Débit réellement mesuré sur la dernière génération, quand il y en a eu une. */
  debitObserve: number | null;
}

export function PanneauPlan({ cible, etatPlan, chargement, debitObserve }: PanneauPlanProps): ReactElement {
  if (cible === null) {
    return <PlanAbsent />;
  }
  const plan = etatPlan.plan;
  return (
    <Card title="Plan de chargement" padding="sm">
      <div className="space-y-4">
        <EnTete cible={cible} etatPlan={etatPlan} />
        {etatPlan.erreur !== null && (
          <p className="text-xs leading-relaxed text-critical">{etatPlan.erreur}</p>
        )}
        {plan === null ? (
          <p className="text-xs text-text-2">Calcul du plan en cours…</p>
        ) : (
          <CorpsPlan
            cible={cible}
            plan={plan}
            etatPlan={etatPlan}
            chargement={chargement}
            debitObserve={debitObserve}
          />
        )}
        <SuiviChargement cible={cible} plan={plan} etatPlan={etatPlan} chargement={chargement} />
      </div>
    </Card>
  );
}
