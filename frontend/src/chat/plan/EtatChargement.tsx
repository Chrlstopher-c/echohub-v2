import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { Badge, Button, Card, type Tone } from '../../shared/design';
import type { CauseEchec, EntreeJournal, PlanDeChargement, ReponsePlan, StatutInference } from '../api/contrats';
import { formaterDuree, formaterHeure, formaterTokens } from './format';

/*
 * État du chargement, sans progression simulée.
 *
 * Le backend ne publie aucun pourcentage — il publie des faits datés. L'écran affiche donc le temps
 * écoulé (qui avance parce que le temps avance) et le journal de la session (qui s'allonge parce
 * qu'une étape s'est réellement produite). La v1 animait 0 → 88 % en six secondes, à vide.
 *
 * Un échec n'est pas un cul-de-sac : il porte sa cause qualifiée, la remédiation du backend, et
 * ouvre sur un plan strictement plus conservateur. Jamais une escalade.
 */

const INTERVALLE_CHRONO_MS = 200;

const TONE_ETAT: Record<StatutInference['etat'], Tone> = {
  inactif: 'neutral',
  en_cours: 'accent',
  pret: 'ok',
  echoue: 'critical',
};

const LIBELLE_ETAT: Record<StatutInference['etat'], string> = {
  inactif: 'aucun modèle chargé',
  en_cours: 'chargement en cours',
  pret: 'modèle prêt',
  echoue: 'chargement échoué',
};

/*
 * Un échec récupérable est ambre : le planificateur peut replier. Le rouge reste réservé à ce qui
 * ne repartira pas d'une simple dégradation — moteur absent, fichier illisible, plan incomplet.
 */
const CAUSES_RECUPERABLES: ReadonlySet<CauseEchec> = new Set<CauseEchec>([
  'vram_insuffisante',
  'vram_non_liberee',
  'ram_insuffisante',
  'contexte_trop_grand',
  'delai_depasse',
  'indeterminee',
]);

const LIBELLE_CAUSE: Record<CauseEchec, string> = {
  vram_insuffisante: 'VRAM insuffisante',
  vram_non_liberee: 'VRAM non rendue par le processus précédent',
  ram_insuffisante: 'RAM hôte insuffisante',
  contexte_trop_grand: 'contexte refusé par le moteur',
  architecture_inconnue: 'architecture inconnue du moteur',
  quantification_incompatible: 'quantification incompatible',
  fichier_illisible: 'fichier de poids illisible',
  moteur_absent: 'moteur non installé',
  moteur_sans_cuda: 'moteur compilé sans CUDA',
  plan_incomplet: 'plan incomplet',
  delai_depasse: 'délai de chargement dépassé',
  annule: 'chargement annulé',
  indeterminee: 'cause indéterminée',
};

function useChrono(actif: boolean, debutMs: number | null): number | null {
  const [maintenant, setMaintenant] = useState<number>(() => Date.now());
  useEffect((): (() => void) | undefined => {
    if (!actif) {
      return undefined;
    }
    setMaintenant(Date.now());
    const minuteur = window.setInterval(() => setMaintenant(Date.now()), INTERVALLE_CHRONO_MS);
    return (): void => window.clearInterval(minuteur);
  }, [actif]);
  return debutMs === null ? null : maintenant - debutMs;
}

const TONE_NIVEAU: Record<EntreeJournal['niveau'], string> = {
  info: 'text-text-2',
  avertissement: 'text-caution',
  erreur: 'text-critical',
};

function JournalSession({ entrees }: { entrees: EntreeJournal[] }): ReactElement | null {
  if (entrees.length === 0) {
    return null;
  }
  return (
    <ol className="max-h-40 space-y-0.5 overflow-y-auto">
      {entrees.map((entree, index) => (
        <li key={`${entree.horodatage}-${index}`} className="flex gap-2 font-mono text-2xs">
          <span className="shrink-0 tabular-nums text-text-3">{formaterHeure(entree.horodatage)}</span>
          <span className="shrink-0 text-text-3">{entree.phase}</span>
          <span className={`flex-1 ${TONE_NIVEAU[entree.niveau]}`}>{entree.message}</span>
        </li>
      ))}
    </ol>
  );
}

function ResumePlanDegrade({ plan }: { plan: PlanDeChargement }): ReactElement {
  return (
    <ul className="space-y-0.5 font-mono text-2xs tabular-nums text-text-2">
      <li>couches GPU : {plan.couches_gpu.valeur} / {plan.couches_totales}</li>
      <li>contexte : {formaterTokens(plan.contexte.valeur)} tokens</li>
      <li>cache KV : {plan.type_cache_kv.valeur}</li>
      <li>niveau de repli : {plan.niveau_degradation}</li>
    </ul>
  );
}

interface EchecProps {
  statut: StatutInference;
  planDegrade: ReponsePlan | null;
  onDemanderDegradation: () => void;
  onAdopterDegradation: (reponse: ReponsePlan) => void;
}

function Echec({ statut, planDegrade, onDemanderDegradation, onAdopterDegradation }: EchecProps): ReactElement {
  const cause = statut.cause ?? 'indeterminee';
  const tone: Tone = CAUSES_RECUPERABLES.has(cause) ? 'caution' : 'critical';
  return (
    <Card level="raised" padding="sm">
      <div className="space-y-2">
        <Badge tone={tone}>{LIBELLE_CAUSE[cause]}</Badge>
        <p className="text-xs leading-relaxed text-text">{statut.message}</p>
        {statut.remediation !== '' && (
          <p className="text-2xs leading-relaxed text-text-2">{statut.remediation}</p>
        )}
        {planDegrade === null ? (
          <Button variant="secondary" size="sm" onClick={onDemanderDegradation}>
            Proposer un plan plus conservateur
          </Button>
        ) : (
          <div className="space-y-2">
            <ResumePlanDegrade plan={planDegrade.plan} />
            <Button variant="primary" size="sm" onClick={() => onAdopterDegradation(planDegrade)}>
              Adopter ce plan
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}

export interface EtatChargementProps {
  statut: StatutInference | null;
  entrees: EntreeJournal[];
  debutMs: number | null;
  planDegrade: ReponsePlan | null;
  onDemanderDegradation: () => void;
  onAdopterDegradation: (reponse: ReponsePlan) => void;
}

export function EtatChargement({
  statut,
  entrees,
  debutMs,
  planDegrade,
  onDemanderDegradation,
  onAdopterDegradation,
}: EtatChargementProps): ReactElement {
  const etat = statut?.etat ?? 'inactif';
  const ecoule = useChrono(etat === 'en_cours', debutMs);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Badge tone={TONE_ETAT[etat]} dot pulse={etat === 'en_cours'}>
          {LIBELLE_ETAT[etat]}
        </Badge>
        {ecoule !== null && etat === 'en_cours' && (
          <span className="font-mono text-xs tabular-nums text-text-2">{formaterDuree(ecoule)}</span>
        )}
      </div>
      {etat === 'en_cours' && <JournalSession entrees={entrees} />}
      {etat === 'echoue' && statut !== null && (
        <Echec
          statut={statut}
          planDegrade={planDegrade}
          onDemanderDegradation={onDemanderDegradation}
          onAdopterDegradation={onAdopterDegradation}
        />
      )}
    </div>
  );
}
