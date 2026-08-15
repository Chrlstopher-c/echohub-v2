import { useCallback, useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { Slider } from '../../shared/design';
import {
  formaterDecimal,
  formaterPlage,
  formaterPlageEntiere,
  type DefinitionCurseur,
  type DefinitionEntier,
  type DefinitionParametre,
  type PlageEntiere,
} from './definitions';

/*
 * Champs de saisie du panneau. Trois règles communes, qui viennent toutes de la même exigence :
 * ce qui est affiché doit être ce qui est retenu.
 *
 * 1. **Aucune valeur n'est inventée.** Un champ vidé vaut `null` et part tel quel au backend ; il
 *    ne retombe pas sur un défaut fabriqué ici. C'est la seule façon de rendre « aucun plafond »
 *    atteignable après qu'un plafond a été posé.
 * 2. **Une saisie hors bornes n'est pas retenue, et le champ le dit.** Elle reste lisible le temps
 *    de la corriger, elle n'est pas envoyée, et quitter le champ y remet la valeur réellement en
 *    vigueur — un nombre affiché ne peut donc pas rester différent de celui qui compte.
 * 3. **Les bornes affichées sont celles du backend** (`definitions.ts`), jamais un arrondi commode.
 */

interface LigneEffetProps {
  readonly plage: string;
  readonly definition: DefinitionParametre;
}

/** Ce que le réglage fait, précédé de sa plage réelle en mono. Jamais une infobulle décorative. */
function LigneEffet({ plage, definition }: LigneEffetProps): ReactElement {
  return (
    <p className="text-2xs leading-snug text-text-3">
      <span className="font-mono tabular-nums text-text-2">{plage}</span>
      {' — '}
      {definition.effet}
      {definition.absence !== '' && ` ${definition.absence}`}
    </p>
  );
}

function afficher(valeur: number | null): string {
  return valeur === null ? '' : String(valeur);
}

function acceptable(nombre: number, plage: PlageEntiere): boolean {
  if (!Number.isInteger(nombre)) {
    return false;
  }
  if (plage.min !== null && nombre < plage.min) {
    return false;
  }
  return plage.max === null || nombre <= plage.max;
}

interface SaisieEntiere {
  readonly texte: string;
  /** Le texte affiché ne correspond pas à la valeur retenue : elle n'a pas été enregistrée. */
  readonly ecart: boolean;
  readonly saisir: (texte: string) => void;
  readonly quitter: () => void;
}

/**
 * Saisie d'un entier avec état local : sans lui, un champ entièrement contrôlé effacerait chaque
 * frappe intermédiaire refusée (« 1 » avant « 12 » quand le minimum vaut 10). La valeur retenue
 * reste la seule source d'autorité — elle reprend la main dès qu'elle change, et à la sortie.
 */
function useSaisieEntiere(
  valeur: number | null,
  plage: PlageEntiere,
  emettre: (valeur: number | null) => void,
  videAutorise: boolean,
): SaisieEntiere {
  const [texte, setTexte] = useState<string>(() => afficher(valeur));
  useEffect((): void => setTexte(afficher(valeur)), [valeur]);

  const saisir = useCallback(
    (saisi: string): void => {
      setTexte(saisi);
      const propre = saisi.trim();
      if (propre === '') {
        if (videAutorise) {
          emettre(null);
        }
        return;
      }
      const nombre = Number(propre);
      if (acceptable(nombre, plage)) {
        emettre(nombre);
      }
    },
    [emettre, plage, videAutorise],
  );

  const quitter = useCallback((): void => setTexte(afficher(valeur)), [valeur]);
  return { texte, ecart: texte.trim() !== afficher(valeur), saisir, quitter };
}

/*
 * Le champ occupe toute la largeur disponible au doigt et retrouve ses 9rem alignés à droite à
 * partir de `lg` : une largeur fixe supposerait la colonne de 416px qui n'existe plus dans un tiroir.
 * `min-h-[44px]` porte la cible tactile sans toucher la densité de bureau.
 */
const CLASSE_CHAMP =
  'min-h-[44px] w-full flex-1 rounded-sm border border-border bg-surface-2 px-2 py-1 text-right '
  + 'font-mono text-xs tabular-nums text-text outline-none focus:border-border-strong '
  + 'lg:min-h-0 lg:w-36 lg:flex-none';

interface EntreeNombreProps {
  readonly id: string;
  readonly libelle: string;
  readonly saisie: SaisieEntiere;
  readonly apres?: ReactElement | null;
}

function EntreeNombre({ id, libelle, saisie, apres = null }: EntreeNombreProps): ReactElement {
  return (
    <div className="flex flex-col items-stretch gap-1 lg:flex-row lg:items-center lg:justify-between lg:gap-3">
      <label htmlFor={id} className="text-xs text-text-2">
        {libelle}
      </label>
      <span className="flex min-w-0 items-center gap-2">
        {apres}
        <input
          id={id}
          type="text"
          inputMode="numeric"
          value={saisie.texte}
          onChange={(evenement) => saisie.saisir(evenement.target.value)}
          onBlur={saisie.quitter}
          className={CLASSE_CHAMP}
        />
      </span>
    </div>
  );
}

function NoteEcart({ visible }: { visible: boolean }): ReactElement | null {
  if (!visible) {
    return null;
  }
  return (
    <p className="text-2xs text-caution">
      Saisie non enregistrée : un entier compris dans les bornes ci-dessous est attendu.
    </p>
  );
}

export interface ChampCurseurProps {
  readonly id: string;
  readonly definition: DefinitionCurseur;
  readonly valeur: number;
  readonly onChanger: (valeur: number) => void;
}

export function ChampCurseur({ id, definition, valeur, onChanger }: ChampCurseurProps): ReactElement {
  const { plage } = definition;
  return (
    <div className="space-y-1">
      <Slider
        id={id}
        label={definition.libelle}
        value={valeur}
        min={plage.min}
        max={plage.max}
        step={plage.pas}
        format={formaterDecimal}
        onChange={onChanger}
      />
      <LigneEffet plage={formaterPlage(plage)} definition={definition} />
    </div>
  );
}

export interface ChampEntierProps {
  readonly id: string;
  readonly definition: DefinitionEntier;
  readonly valeur: number;
  readonly onChanger: (valeur: number) => void;
}

/** Entier obligatoire : le vider n'efface rien, le champ reprend simplement la valeur en vigueur. */
export function ChampEntier({ id, definition, valeur, onChanger }: ChampEntierProps): ReactElement {
  const emettre = useCallback(
    (recu: number | null): void => {
      if (recu !== null) {
        onChanger(recu);
      }
    },
    [onChanger],
  );
  const saisie = useSaisieEntiere(valeur, definition.plage, emettre, false);
  return (
    <div className="space-y-1">
      <EntreeNombre id={id} libelle={definition.libelle} saisie={saisie} />
      <NoteEcart visible={saisie.ecart} />
      <LigneEffet plage={formaterPlageEntiere(definition.plage)} definition={definition} />
    </div>
  );
}

export interface ChampEntierOptionnelProps {
  readonly id: string;
  readonly definition: DefinitionEntier;
  readonly valeur: number | null;
  /** Mot qui NOMME l'absence de valeur : « aucun plafond », « aléatoire ». */
  readonly etiquetteVide: string;
  readonly onChanger: (valeur: number | null) => void;
}

/** Entier effaçable : champ vide = `null` envoyé au backend, et l'état vide est nommé, pas deviné. */
export function ChampEntierOptionnel(props: ChampEntierOptionnelProps): ReactElement {
  const { id, definition, valeur, etiquetteVide, onChanger } = props;
  const saisie = useSaisieEntiere(valeur, definition.plage, onChanger, true);
  return (
    <div className="space-y-1">
      <EntreeNombre
        id={id}
        libelle={definition.libelle}
        saisie={saisie}
        apres={<EtatVide vide={valeur === null} etiquette={etiquetteVide} onEffacer={() => onChanger(null)} />}
      />
      <NoteEcart visible={saisie.ecart} />
      <LigneEffet plage={formaterPlageEntiere(definition.plage)} definition={definition} />
    </div>
  );
}

interface EtatVideProps {
  readonly vide: boolean;
  readonly etiquette: string;
  readonly onEffacer: () => void;
}

function EtatVide({ vide, etiquette, onEffacer }: EtatVideProps): ReactElement {
  if (vide) {
    return <span className="shrink-0 text-2xs text-text-3">{etiquette}</span>;
  }
  // Bordé, donc lisible comme un contrôle : cliquer vide le champ et pose l'état que le mot nomme.
  return (
    <button
      type="button"
      onClick={onEffacer}
      className="min-h-[44px] min-w-[44px] shrink-0 rounded-xs border border-border px-1.5 py-0.5
        text-2xs text-text-2 transition-colors duration-fast hover:border-border-strong
        hover:text-text lg:min-h-0 lg:min-w-0"
    >
      {etiquette}
    </button>
  );
}

export interface ChampTexteProps {
  readonly id: string;
  readonly definition: DefinitionParametre;
  readonly valeur: string;
  readonly lignes: number;
  readonly exemple: string;
  readonly onChanger: (valeur: string) => void;
}

export function ChampTexte({ id, definition, valeur, lignes, exemple, onChanger }: ChampTexteProps): ReactElement {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs text-text-2">
        {definition.libelle}
      </label>
      <textarea
        id={id}
        rows={lignes}
        value={valeur}
        placeholder={exemple}
        onChange={(evenement) => onChanger(evenement.target.value)}
        className="w-full resize-y rounded-sm border border-border bg-surface-2 px-2 py-1.5 text-sm
          text-text outline-none placeholder:text-text-3 focus:border-border-strong"
      />
      <p className="text-2xs leading-snug text-text-3">{definition.effet}</p>
    </div>
  );
}
