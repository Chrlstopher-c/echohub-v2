import type { ReactElement } from 'react';
import { Badge, Slider, TONE_VAR, type SliderZone } from '../../shared/design';
import type { PlanDeChargement } from '../api/contrats';
import { formaterDebit, formaterTokens } from './format';
import {
  CONTEXTE_DEBIT_MESURE_HAUT,
  DEBIT_REPERE_MAX,
  PROVENANCE_REPERES,
  REPERES_DEBIT,
} from './reperes-debit';

/*
 * L'arbitrage central du produit, rendu manipulable : ce que coûte un contexte plus large.
 *
 * Le curseur exprime une DEMANDE. Le plan affiché à côté dit ce que la machine accorde. Quand les
 * deux diffèrent, le plafonnement est nommé — la v1 rabotait en silence et laissait croire à
 * l'utilisateur qu'il tournait avec ce qu'il avait demandé.
 *
 * Les débits montrés sont des mesures, jamais une prédiction : deux points relevés sur une machine
 * et un modèle précis. Aucune courbe n'est tracée entre eux, aucune valeur n'est interpolée pour le
 * modèle courant — ce serait exactement la manière dont la v1 fabriquait ses chiffres.
 */

/* Granularité du curseur : une commodité d'interface, pas une contrainte machine. */
const PAS_CONTEXTE = 1024;

function zonesDebit(max: number): SliderZone[] {
  if (max <= CONTEXTE_DEBIT_MESURE_HAUT) {
    return [];
  }
  // Au-delà du dernier contexte au débit mesuré haut, la seule mesure disponible montre -52 %.
  return [{ from: CONTEXTE_DEBIT_MESURE_HAUT + 1, tone: 'caution' }];
}

function BarreRepere({ contexte, tokensParSeconde }: { contexte: number; tokensParSeconde: number }): ReactElement {
  const largeur = `${((tokensParSeconde / DEBIT_REPERE_MAX) * 100).toFixed(1)}%`;
  return (
    <li className="flex items-center gap-2">
      {/* Colonnes resserrées au doigt, densité de bureau restaurée en `lg:` : les deux chiffres
          restent alignés entre eux, mais ne mangent plus la barre dans un tiroir étroit. */}
      <span className="w-12 shrink-0 font-mono text-2xs tabular-nums text-text-2 lg:w-16">
        {formaterTokens(contexte)}
      </span>
      <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-2">
        <span className="block h-full rounded-full" style={{ width: largeur, backgroundColor: TONE_VAR.kv }} />
      </span>
      <span className="w-16 shrink-0 text-right font-mono text-2xs tabular-nums text-text lg:w-20">
        {formaterDebit(tokensParSeconde)}
      </span>
    </li>
  );
}

function ReperesMesures(): ReactElement {
  return (
    <div className="min-w-0">
      <p className="mb-1.5 break-words text-2xs text-text-2">Débits mesurés — {PROVENANCE_REPERES}</p>
      <ul className="space-y-1">
        {REPERES_DEBIT.map((repere) => (
          <BarreRepere key={repere.contexte} contexte={repere.contexte} tokensParSeconde={repere.tokensParSeconde} />
        ))}
      </ul>
      <p className="mt-1.5 text-2xs leading-relaxed text-text-3">
        Deux points relevés, pas une courbe : aucun débit n’est prédit pour un autre modèle ni pour un
        contexte intermédiaire.
      </p>
    </div>
  );
}

function Plafonnement({ plan }: { plan: PlanDeChargement }): ReactElement | null {
  const contexte = plan.contexte;
  if (!contexte.plafonnee || contexte.valeur_demandee === null) {
    return null;
  }
  return (
    <Badge tone="caution">
      plafonné — demandé {formaterTokens(contexte.valeur_demandee)}, accordé {formaterTokens(contexte.valeur)}
    </Badge>
  );
}

export interface ArbitrageContexteProps {
  plan: PlanDeChargement;
  /** Contexte demandé par l'utilisateur ; `null` tant qu'il laisse le planificateur décider. */
  contexteDemande: number | null;
  contexteMaximum: number;
  /** Débit réellement mesuré sur la dernière génération de cette conversation, s'il y en a une. */
  debitObserve: number | null;
  onChangerContexte: (contexte: number) => void;
  desactive: boolean;
}

export function ArbitrageContexte({
  plan,
  contexteDemande,
  contexteMaximum,
  debitObserve,
  onChangerContexte,
  desactive,
}: ArbitrageContexteProps): ReactElement {
  const valeur = contexteDemande ?? plan.contexte.valeur;
  return (
    <div className="min-w-0 space-y-3">
      <Slider
        id="contexte"
        label="Contexte demandé"
        value={Math.min(valeur, contexteMaximum)}
        min={PAS_CONTEXTE}
        max={contexteMaximum}
        step={PAS_CONTEXTE}
        zones={zonesDebit(contexteMaximum)}
        onChange={onChangerContexte}
        format={(v) => `${formaterTokens(v)} tokens`}
        disabled={desactive}
      />
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="kv">plan : {formaterTokens(plan.contexte.valeur)} tokens</Badge>
        <Plafonnement plan={plan} />
        {debitObserve !== null && (
          <Badge tone="ok" dot>
            mesuré ici : {formaterDebit(debitObserve)}
          </Badge>
        )}
      </div>
      <p className="break-words font-mono text-2xs leading-relaxed text-text-3">
        {plan.contexte.justification}
      </p>
      <ReperesMesures />
    </div>
  );
}
