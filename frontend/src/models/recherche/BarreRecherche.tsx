import { useState, type ChangeEvent, type ReactElement } from 'react';
import { Feuille, cn } from '../../shared/design';
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
 *
 * Sous 1024 px, treize puces de filtre occuperaient la moitié de l'écran avant le premier résultat.
 * Elles passent donc dans un tiroir latéral, dont le déclencheur affiche le NOMBRE de filtres
 * actifs : un filtre replié qui ne se compte pas est un filtre oublié, et une liste vide devient
 * inexplicable. Au-dessus du seuil, `Feuille` est un passe-plat — la barre est celle d'avant.
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

/* `text-base` sous le seuil : à moins de 16 px, iOS zoome de lui-même à la mise au point du champ
 * et l'utilisateur se retrouve dans une page décalée qu'il doit repincer. La taille de bureau
 * revient à `lg:`. La hauteur suit la cible tactile de 44 px. */
const CHAMP =
  'min-h-[44px] rounded-sm border border-border bg-surface-2 px-2.5 text-base text-text outline-none ' +
  'lg:h-8 lg:min-h-0 lg:text-sm focus-visible:shadow-[0_0_0_3px_var(--ring)]';

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
        'rounded-xs px-2.5 text-xs font-medium transition-colors duration-fast ease-out',
        'min-h-[44px] min-w-[44px] lg:h-7 lg:min-h-0 lg:min-w-0',
        actif ? 'bg-accent-soft text-accent' : 'bg-surface-2 text-text-2 hover:text-text',
      )}
    >
      {libelle}
    </button>
  );
}

function LigneSaisie({
  recherche,
  declencheurFiltres,
}: {
  recherche: EtatRecherche;
  /** Ouverture du tiroir de filtres — rendu ici pour partager la ligne du tri sous le seuil. */
  declencheurFiltres: ReactElement;
}): ReactElement {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        value={recherche.critere.requete}
        placeholder="Chercher un modèle sur Hugging Face"
        onChange={(evenement: ChangeEvent<HTMLInputElement>): void =>
          recherche.definirRequete(evenement.target.value)
        }
        className={cn(CHAMP, 'w-full min-w-0 lg:w-auto lg:grow')}
        aria-label="Recherche Hugging Face"
      />
      <select
        value={recherche.critere.tri}
        onChange={(evenement: ChangeEvent<HTMLSelectElement>): void => {
          // Le cast reste dans la valeur du `<select>`, dont les options sont exactement `TRIS`.
          recherche.definirTri(evenement.target.value as TriRecherche);
        }}
        className={cn(CHAMP, 'min-w-0 grow lg:grow-0')}
        aria-label="Trier par"
      >
        {TRIS.map((tri) => (
          <option key={tri.valeur} value={tri.valeur}>
            {tri.libelle}
          </option>
        ))}
      </select>
      {declencheurFiltres}
    </div>
  );
}

function BoutonFiltres({ actifs, onOuvrir }: { actifs: number; onOuvrir: () => void }): ReactElement {
  return (
    <button
      type="button"
      onClick={onOuvrir}
      aria-haspopup="dialog"
      className={cn(
        'inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-sm border border-border',
        'bg-surface-2 px-3 text-xs font-medium text-text-2 outline-none lg:hidden',
        'transition-colors duration-fast ease-out hover:text-text',
        'focus-visible:shadow-[0_0_0_3px_var(--ring)]',
        actifs > 0 && 'border-accent text-accent',
      )}
    >
      Filtres
      {actifs > 0 && <span className="font-mono tabular-nums">{actifs}</span>}
    </button>
  );
}

export interface BarreRechercheProps {
  recherche: EtatRecherche;
  vocabulaire: VocabulaireCapacites;
}

export function BarreRecherche({ recherche, vocabulaire }: BarreRechercheProps): ReactElement {
  const { critere } = recherche;
  const [tiroirOuvert, setTiroirOuvert] = useState<boolean>(false);
  const actifs = critere.formats.length + critere.capacites.length;

  return (
    <div className="space-y-3">
      <LigneSaisie
        recherche={recherche}
        declencheurFiltres={
          <BoutonFiltres actifs={actifs} onOuvrir={(): void => setTiroirOuvert(true)} />
        }
      />
      <Feuille
        ouverte={tiroirOuvert}
        onFermer={(): void => setTiroirOuvert(false)}
        cote="droite"
        titre="Filtres"
      >
        <div className="space-y-3 p-3 lg:p-0">
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
      </Feuille>
    </div>
  );
}
