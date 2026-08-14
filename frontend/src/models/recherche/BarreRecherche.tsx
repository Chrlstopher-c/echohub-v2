import type { ChangeEvent, ReactElement } from 'react';
import { cn } from '../../shared/design';
import type { FormatRecherche, TriRecherche } from '../api/types';
import { FiltreCapacites } from './FiltreCapacites';
import type { VocabulaireCapacites } from './useDefinitionsCapacites';
import type { EtatRecherche } from './useRecherche';

/*
 * Saisie et filtres de la recherche.
 *
 * Les formats sont des étiquettes déclarées par le Hub, pas des vérifications de contenu : un dépôt
 * étiqueté GGUF peut n'en contenir aucun. Le filtre sert à réduire la liste, jamais à garantir.
 *
 * Les capacités sont de la même nature — des déclarations lues, pas des essais — mais d'une source
 * différente : le Hub ne les publie pas, le backend les déduit. Elles ont donc leur propre bloc,
 * leur propre vocabulaire chargé depuis l'API, et n'interfèrent pas avec les formats : les deux
 * filtres se cumulent dans le même critère de recherche.
 */

const FORMATS: ReadonlyArray<{ valeur: FormatRecherche; libelle: string }> = [
  { valeur: 'gguf', libelle: 'GGUF' },
  { valeur: 'awq', libelle: 'AWQ' },
  { valeur: 'gptq', libelle: 'GPTQ' },
  { valeur: 'safetensors', libelle: 'safetensors' },
];

const TRIS: ReadonlyArray<{ valeur: TriRecherche; libelle: string }> = [
  { valeur: 'downloads', libelle: 'Téléchargements' },
  { valeur: 'likes', libelle: 'Mentions' },
  { valeur: 'trending_score', libelle: 'Tendance' },
  { valeur: 'last_modified', libelle: 'Modification' },
  { valeur: 'created_at', libelle: 'Création' },
];

const CHAMP =
  'h-8 rounded-sm border border-border bg-surface-2 px-2.5 text-sm text-text outline-none ' +
  'focus-visible:shadow-[0_0_0_3px_var(--ring)]';

function Puce({
  actif,
  libelle,
  onClick,
}: {
  actif: boolean;
  libelle: string;
  onClick: () => void;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={actif}
      className={cn(
        'h-7 rounded-xs px-2.5 text-xs font-medium transition-colors duration-fast ease-out',
        actif ? 'bg-accent-soft text-accent' : 'bg-surface-2 text-text-2 hover:text-text',
      )}
    >
      {libelle}
    </button>
  );
}

function LigneSaisie({ recherche }: { recherche: EtatRecherche }): ReactElement {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        value={recherche.critere.requete}
        placeholder="Chercher un modèle sur Hugging Face"
        onChange={(evenement: ChangeEvent<HTMLInputElement>): void =>
          recherche.definirRequete(evenement.target.value)
        }
        className={cn(CHAMP, 'grow')}
        aria-label="Recherche Hugging Face"
      />
      <select
        value={recherche.critere.tri}
        onChange={(evenement: ChangeEvent<HTMLSelectElement>): void => {
          // Le cast reste dans la valeur du `<select>`, dont les options sont exactement `TRIS`.
          recherche.definirTri(evenement.target.value as TriRecherche);
        }}
        className={CHAMP}
        aria-label="Trier par"
      >
        {TRIS.map((tri) => (
          <option key={tri.valeur} value={tri.valeur}>
            {tri.libelle}
          </option>
        ))}
      </select>
    </div>
  );
}

export interface BarreRechercheProps {
  recherche: EtatRecherche;
  vocabulaire: VocabulaireCapacites;
}

export function BarreRecherche({ recherche, vocabulaire }: BarreRechercheProps): ReactElement {
  const { critere } = recherche;
  return (
    <div className="space-y-3">
      <LigneSaisie recherche={recherche} />
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-2xs text-text-3">Formats annoncés</span>
        {FORMATS.map((format) => (
          <Puce
            key={format.valeur}
            libelle={format.libelle}
            actif={critere.formats.includes(format.valeur)}
            onClick={(): void => recherche.basculerFormat(format.valeur)}
          />
        ))}
      </div>
      <FiltreCapacites
        vocabulaire={vocabulaire}
        selection={critere.capacites}
        onBasculer={recherche.basculerCapacite}
        onEffacer={recherche.effacerCapacites}
      />
    </div>
  );
}
