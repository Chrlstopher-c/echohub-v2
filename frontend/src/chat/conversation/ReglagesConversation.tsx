import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { Button, Modal, Slider } from '../../shared/design';
import type { MajReglages, ParametresEchantillonnage, ReglagesConversation as Reglages } from '../api/contrats';

/*
 * Prompt système et paramètres d'échantillonnage de la conversation.
 *
 * Les bornes reproduisent celles que le backend valide (`ParametresEchantillonnage`) : proposer un
 * réglage qui serait refusé à l'enregistrement ferait perdre la saisie sans expliquer pourquoi.
 * Les valeurs par défaut ne sont pas rappelées ici — c'est le backend qui les porte.
 */

const PLAFOND_MAX_TOKENS = 262_144;

interface ChampNombreProps {
  libelle: string;
  valeur: number;
  min: number;
  max: number;
  onChanger: (valeur: number) => void;
}

function ChampNombre({ libelle, valeur, min, max, onChanger }: ChampNombreProps): ReactElement {
  return (
    <label className="flex items-center justify-between gap-3">
      <span className="text-xs text-text-2">{libelle}</span>
      <input
        type="number"
        value={valeur}
        min={min}
        max={max}
        onChange={(evenement) => onChanger(Number(evenement.target.value))}
        className="w-28 rounded-sm border border-border bg-surface-2 px-2 py-1 text-right font-mono text-xs
          tabular-nums text-text outline-none focus:border-border-strong"
      />
    </label>
  );
}

interface ParametresProps {
  parametres: ParametresEchantillonnage;
  onChanger: (parametres: ParametresEchantillonnage) => void;
}

type Modifier = (patch: Partial<ParametresEchantillonnage>) => void;

interface CurseursProps {
  parametres: ParametresEchantillonnage;
  modifier: Modifier;
}

function Curseurs({ parametres, modifier }: CurseursProps): ReactElement {
  return (
    <>
      <Slider
        id="temperature"
        label="Température"
        value={parametres.temperature}
        min={0}
        max={2}
        step={0.05}
        format={(v) => v.toFixed(2)}
        onChange={(temperature) => modifier({ temperature })}
      />
      <Slider
        id="top-p"
        label="Top-p"
        value={parametres.top_p}
        min={0.01}
        max={1}
        step={0.01}
        format={(v) => v.toFixed(2)}
        onChange={(top_p) => modifier({ top_p })}
      />
      <Slider
        id="penalite"
        label="Pénalité de répétition"
        value={parametres.penalite_repetition}
        min={0}
        max={2}
        step={0.01}
        format={(v) => v.toFixed(2)}
        onChange={(penalite_repetition) => modifier({ penalite_repetition })}
      />
    </>
  );
}

function Entiers({ parametres, modifier }: CurseursProps): ReactElement {
  return (
    <>
      <ChampNombre
        libelle="Top-k"
        valeur={parametres.top_k}
        min={0}
        max={1000}
        onChanger={(top_k) => modifier({ top_k })}
      />
      <ChampNombre
        libelle="Tokens générés au maximum"
        valeur={parametres.max_tokens}
        min={1}
        max={PLAFOND_MAX_TOKENS}
        onChanger={(max_tokens) => modifier({ max_tokens })}
      />
    </>
  );
}

function ChampsParametres({ parametres, onChanger }: ParametresProps): ReactElement {
  const modifier: Modifier = (patch) => onChanger({ ...parametres, ...patch });
  return (
    <div className="space-y-3">
      <Curseurs parametres={parametres} modifier={modifier} />
      <Entiers parametres={parametres} modifier={modifier} />
    </div>
  );
}

interface ChampPromptProps {
  valeur: string;
  onChanger: (valeur: string) => void;
}

function ChampPromptSysteme({ valeur, onChanger }: ChampPromptProps): ReactElement {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-text-2">Prompt système</span>
      <textarea
        rows={5}
        value={valeur}
        onChange={(evenement) => onChanger(evenement.target.value)}
        placeholder="Instructions permanentes envoyées au modèle avant chaque échange."
        className="w-full resize-y rounded-sm border border-border bg-surface-2 px-2 py-1.5 text-sm
          text-text outline-none placeholder:text-text-3 focus:border-border-strong"
      />
    </label>
  );
}

function PiedReglages({ onFermer, onEnregistrer }: { onFermer: () => void; onEnregistrer: () => void }): ReactElement {
  return (
    <>
      <Button variant="ghost" size="sm" onClick={onFermer}>
        Annuler
      </Button>
      <Button variant="primary" size="sm" onClick={onEnregistrer}>
        Enregistrer
      </Button>
    </>
  );
}

export interface ReglagesConversationProps {
  ouvert: boolean;
  reglages: Reglages;
  onFermer: () => void;
  onEnregistrer: (patch: MajReglages) => void;
}

export function ReglagesConversation({
  ouvert,
  reglages,
  onFermer,
  onEnregistrer,
}: ReglagesConversationProps): ReactElement {
  const [brouillon, setBrouillon] = useState<Reglages>(reglages);
  // Rouvrir la modale doit repartir de l'état enregistré, pas d'une saisie abandonnée.
  useEffect((): void => setBrouillon(reglages), [reglages, ouvert]);

  const enregistrer = (): void => {
    onEnregistrer({ prompt_systeme: brouillon.prompt_systeme, parametres: brouillon.parametres });
    onFermer();
  };

  return (
    <Modal
      open={ouvert}
      onClose={onFermer}
      title="Réglages de la conversation"
      footer={<PiedReglages onFermer={onFermer} onEnregistrer={enregistrer} />}
    >
      <div className="space-y-4">
        <ChampPromptSysteme
          valeur={brouillon.prompt_systeme}
          onChanger={(prompt_systeme) => setBrouillon({ ...brouillon, prompt_systeme })}
        />
        <ChampsParametres
          parametres={brouillon.parametres}
          onChanger={(parametres) => setBrouillon({ ...brouillon, parametres })}
        />
      </div>
    </Modal>
  );
}
