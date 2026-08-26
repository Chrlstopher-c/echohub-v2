/*
 * Un appel d'outil, lisible d'un coup d'œil : quel outil, sur quoi, et où il en est.
 *
 * Remplace l'ancien rendu scindé « entrée » / « sortie » dans un bloc anonyme : il fallait déplier
 * pour savoir jusqu'à l'outil concerné. Ici la ligne repliée dit tout — libellé, cible en mono,
 * état à droite — et le dépliage ne sert qu'au détail : l'entrée exacte, puis le résultat complet.
 *
 * Grammaire visuelle du panneau de plan : hiérarchie par la taille et la couleur du texte, mesures
 * en mono tabulaire, badge seulement quand il porte un état (en cours, échec). Un appel terminé
 * n'a PAS de badge — la sobriété est l'état normal, la couleur est réservée à ce qui se passe.
 */

import { AnimatePresence, motion } from 'framer-motion';
import { useId, useState } from 'react';
import type { ReactElement } from 'react';
import { Badge, cn, fadeUp } from '../../shared/design';
import { Chevron } from './Chevron';
import { IconeDeCarte } from './icones-outils';
import type { AppelLisible } from './lecture-appel';

const NOMBRE = new Intl.NumberFormat('fr-FR');

/* Un résultat peut faire des milliers de caractères : déplié, il défile chez lui plutôt que de
 * pousser la réponse hors de l'écran. */
const CLASSE_DEFILEMENT = 'max-h-64 overflow-y-auto overflow-x-auto overscroll-contain';

function EtatCarte({ appel }: { readonly appel: AppelLisible }): ReactElement | null {
  if (appel.etat === 'en_cours') {
    return (
      <Badge tone="accent" dot pulse>
        en cours
      </Badge>
    );
  }
  if (appel.etat === 'interrompu') {
    return <Badge tone="caution">interrompu</Badge>;
  }
  if (appel.etat === 'echec') {
    // Ambre et non rouge : un outil qui échoue se retente, c'est la définition de l'erreur
    // récupérable dans la palette (DESIGN.md). Le rouge dirait que rien ne repartira.
    return <Badge tone="caution">échec</Badge>;
  }
  return null;
}

function MesureSortie({ appel }: { readonly appel: AppelLisible }): ReactElement | null {
  if (appel.etat !== 'termine' || appel.sortie === '') {
    return null;
  }
  return (
    <span className="shrink-0 font-mono text-2xs tabular-nums text-text-3">
      {NOMBRE.format(appel.sortie.length)} car.
    </span>
  );
}

interface EnTeteProps {
  appel: AppelLisible;
  ouvert: boolean;
  cible: string;
  onBasculer: () => void;
}

function EnTeteCarte({ appel, ouvert, cible, onBasculer }: EnTeteProps): ReactElement {
  return (
    <button
      type="button"
      onClick={onBasculer}
      aria-expanded={ouvert}
      aria-controls={cible}
      className={cn(
        // Une seule ligne tant qu'elle tient ; à 390 px le badge et la mesure retombent dessous
        // plutôt que d'écraser la cible — même règle que les entêtes du panneau de plan.
        'flex w-full min-h-[44px] flex-wrap items-center gap-x-2 gap-y-1 rounded-sm px-2.5 py-2',
        'text-left transition-colors duration-fast ease-out hover:bg-surface-2 lg:min-h-0 lg:py-1.5',
        'focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--ring)]',
      )}
    >
      <Chevron ouvert={ouvert} />
      <span className="text-text-3">
        <IconeDeCarte icone={appel.icone} />
      </span>
      <span className="shrink-0 text-xs font-medium text-text-2">{appel.libelle}</span>
      {appel.cible !== null && (
        <span className="min-w-0 flex-1 truncate font-mono text-2xs text-text-3" title={appel.cible}>
          {appel.cible}
        </span>
      )}
      <MesureSortie appel={appel} />
      <EtatCarte appel={appel} />
    </button>
  );
}

function Sortie({ appel }: { readonly appel: AppelLisible }): ReactElement {
  if (appel.sortie === '') {
    return (
      <p className="text-2xs text-text-3">
        {appel.etat === 'en_cours' ? 'Exécution en cours…' : "L'outil n'a rien rendu."}
      </p>
    );
  }
  return (
    <p
      className={cn(
        'whitespace-pre-wrap break-words text-xs leading-relaxed',
        appel.etat === 'echec' ? 'text-caution' : 'text-text-2',
      )}
    >
      {appel.sortie}
    </p>
  );
}

/*
 * Le détail garde les deux temps de l'appel — la demande exacte, puis ce qu'elle a rapporté —
 * parce qu'une recherche hors sujet s'explique presque toujours par une requête mal formulée.
 * Mais il ne s'ouvre QUE si on le demande : c'est le renversement par rapport à l'ancien rendu.
 */
function DetailCarte({ appel }: { readonly appel: AppelLisible }): ReactElement {
  return (
    <div className={cn('space-y-2 border-t border-border px-2.5 py-2', CLASSE_DEFILEMENT)}>
      <div>
        <span className="font-mono text-2xs uppercase tracking-wide text-text-3">demande</span>
        <p className="whitespace-pre-wrap break-words font-mono text-2xs leading-relaxed text-text-2">
          {appel.entree}
        </p>
      </div>
      <div>
        <span className="font-mono text-2xs uppercase tracking-wide text-text-3">résultat</span>
        <Sortie appel={appel} />
      </div>
    </div>
  );
}

export interface CarteOutilProps {
  readonly appel: AppelLisible;
}

export function CarteOutil({ appel }: CarteOutilProps): ReactElement {
  const [ouvert, setOuvert] = useState<boolean>(false);
  const cible = useId();
  return (
    // Surface avant bordure (DESIGN.md) : la carte se détache du fond par sa teinte, le trait
    // n'apparaît qu'à l'intérieur, entre l'entête et le détail déplié.
    <section className="max-w-full rounded-sm bg-surface">
      <EnTeteCarte appel={appel} ouvert={ouvert} cible={cible} onBasculer={() => setOuvert(!ouvert)} />
      <AnimatePresence initial={false}>
        {ouvert && (
          <motion.div id={cible} variants={fadeUp} initial="hidden" animate="visible" exit="exit">
            <DetailCarte appel={appel} />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
