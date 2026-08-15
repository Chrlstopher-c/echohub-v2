import type { ReactElement, ReactNode } from 'react';
import { Badge } from '../../shared/design';
import type { PlanDeChargement, ValeurJustifiee } from '../api/contrats';
import { formaterOctets, formaterPourcentage, formaterTokens } from './format';

/*
 * Chaque valeur du plan avec la phrase qui l'a produite. Le texte vient du planificateur et n'est
 * ni reformulé ni résumé ici : c'est lui qui sait pourquoi 28 couches et pas 41.
 *
 * Les variables d'environnement REFUSÉES sont affichées au même titre que les autres. Une absence
 * décidée est un réglage — `GGML_CUDA_ENABLE_UNIFIED_MEMORY` non posée sous WSL2 est la différence
 * entre un modèle inutilisable et un chargement en 12 secondes.
 */

interface LigneProps {
  libelle: string;
  valeur: string;
  justification: string;
  plafonnee: boolean;
  demande?: string;
}

function Ligne({ libelle, valeur, justification, plafonnee, demande }: LigneProps): ReactElement {
  return (
    <li className="py-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-xs text-text-2">{libelle}</span>
        <span className="break-all font-mono text-xs tabular-nums text-text">{valeur}</span>
      </div>
      {plafonnee && demande !== undefined && (
        <div className="mt-1">
          <Badge tone="caution">plafonné — demandé {demande}</Badge>
        </div>
      )}
      <p className="mt-0.5 text-2xs leading-relaxed text-text-3">{justification}</p>
    </li>
  );
}

function ligneDepuis<T>(
  libelle: string,
  champ: ValeurJustifiee<T>,
  rendu: (valeur: T) => string,
): ReactElement {
  return (
    <Ligne
      key={libelle}
      libelle={libelle}
      valeur={rendu(champ.valeur)}
      justification={champ.justification}
      plafonnee={champ.plafonnee}
      demande={champ.valeur_demandee !== null ? rendu(champ.valeur_demandee) : undefined}
    />
  );
}

function Section({ titre, children }: { titre: string; children: ReactNode }): ReactElement {
  return (
    <div>
      <h3 className="mb-1 text-2xs font-medium uppercase tracking-wide text-text-3">{titre}</h3>
      {children}
    </div>
  );
}

function Environnement({ plan }: { plan: PlanDeChargement }): ReactElement | null {
  if (plan.variables_environnement.length === 0 && plan.variables_refusees.length === 0) {
    return null;
  }
  return (
    <Section titre="Environnement du moteur">
      <ul className="divide-y divide-border">
        {plan.variables_environnement.map((variable) => (
          <li key={variable.nom} className="py-1.5">
            {/* `break-all` : un nom de variable d'environnement est un mot insécable long, il
                déborderait du tiroir au lieu de passer à la ligne. */}
            <span className="block break-all font-mono text-xs text-text">
              {variable.nom}={variable.valeur}
            </span>
            <p className="mt-0.5 text-2xs leading-relaxed text-text-3">{variable.justification}</p>
          </li>
        ))}
        {plan.variables_refusees.map((refusee) => (
          <li key={refusee.nom} className="py-1.5">
            <span className="break-all font-mono text-xs text-text-2 line-through">{refusee.nom}</span>
            <Badge tone="caution" className="ml-1.5">
              non posée
            </Badge>
            <p className="mt-0.5 text-2xs leading-relaxed text-text-3">{refusee.raison}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Ejections({ plan }: { plan: PlanDeChargement }): ReactElement | null {
  if (plan.ejections_requises.length === 0) {
    return null;
  }
  return (
    <Section titre="À éjecter avant chargement">
      <ul className="space-y-1.5">
        {plan.ejections_requises.map((ejection) => (
          <li key={ejection.identifiant}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 truncate text-xs text-text">{ejection.identifiant}</span>
              <span className="shrink-0 font-mono text-xs tabular-nums text-mem-vram">
                +{formaterOctets(ejection.vram_liberee_octets)}
              </span>
            </div>
            <p className="mt-0.5 text-2xs leading-relaxed text-text-3">{ejection.raison}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Avertissements({ messages }: { messages: string[] }): ReactElement | null {
  if (messages.length === 0) {
    return null;
  }
  return (
    <Section titre="Avertissements">
      <ul className="space-y-1">
        {messages.map((message) => (
          <li key={message} className="text-2xs leading-relaxed text-caution">
            {message}
          </li>
        ))}
      </ul>
    </Section>
  );
}

export interface JustificationsProps {
  plan: PlanDeChargement;
}

export function Justifications({ plan }: JustificationsProps): ReactElement {
  const lignes: ReactElement[] = [
    ligneDepuis('Moteur', plan.moteur, (v) => v),
    ligneDepuis('Couches sur GPU', plan.couches_gpu, (v) => `${v} / ${plan.couches_totales}`),
    ligneDepuis('Contexte', plan.contexte, (v) => `${formaterTokens(v)} tokens`),
    ligneDepuis('Batch', plan.batch, (v) => formaterTokens(v)),
    ligneDepuis('Cache KV', plan.type_cache_kv, (v) => v),
    ligneDepuis('Flash attention', plan.flash_attention, (v) => (v ? 'activée' : 'désactivée')),
  ];
  if (plan.utilisation_memoire_gpu !== null) {
    lignes.push(ligneDepuis('VRAM préallouée (vLLM)', plan.utilisation_memoire_gpu, formaterPourcentage));
  }
  return (
    <div className="min-w-0 space-y-3">
      <Section titre="Valeurs du plan">
        <ul className="divide-y divide-border">{lignes}</ul>
      </Section>
      <Environnement plan={plan} />
      <Ejections plan={plan} />
      <Avertissements messages={plan.avertissements} />
    </div>
  );
}
