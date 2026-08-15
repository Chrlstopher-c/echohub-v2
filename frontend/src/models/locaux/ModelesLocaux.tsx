import { AnimatePresence, motion } from 'framer-motion';
import { useState } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { Badge, Button, Card, cn, fadeUp, MenuContextuel } from '../../shared/design';
import type { ModeleEnregistre, RapportCoherence } from '../api/types';
import { journal } from '../api/client';
import { verifierCoherence } from '../api/registre';
import { DossiersNonInscrits } from './DossiersNonInscrits';
import { useInventaireDisque } from './useInventaireDisque';
import { PastilleFaisabilite } from '../faisabilite/Faisabilite';
import { evaluer, type BudgetMemoire } from '../faisabilite/evaluation';
import { entier, octetsLisibles } from '../format';
import type { EtatModelesLocaux } from './useModelesLocaux';

/*
 * Modèles présents sur le disque.
 *
 * Un champ vide veut dire « pas encore mesuré », jamais « estimé » : `nb_couches` absent signifie
 * que l'en-tête n'a pas été lu, et l'interface le dit avec ces mots-là. C'est cette distinction que
 * la v1 perdait en recopiant des estimations en base, ensuite traitées comme des faits.
 */

function Champ({ libelle, children }: { libelle: string; children: ReactNode }): ReactElement {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-2xs text-text-3">{libelle}</dt>
      <dd className="min-w-0 truncate text-right font-mono text-2xs tabular-nums text-text-2">{children}</dd>
    </div>
  );
}

function EtatMetadonnees({ modele }: { modele: ModeleEnregistre }): ReactElement {
  if (modele.nb_couches === null) {
    return <Badge tone="caution">métadonnées non lues</Badge>;
  }
  return <Badge tone="ok">{`${entier(modele.nb_couches)} couches lues`}</Badge>;
}

/* Étoile pleine ou vide selon l'état : une seule forme, deux remplissages — on lit l'état sans
   comparer deux icônes différentes. */
function Etoile({ marque }: { marque: boolean }): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden="true"
      fill={marque ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round">
      <path d="M8 2l1.8 3.9 4.2.5-3.1 2.9.8 4.2L8 11.6 4.3 13.5l.8-4.2L2 6.4l4.2-.5L8 2z" />
    </svg>
  );
}

function EnTeteModele({
  modele,
  budget,
  onBasculerFavori,
}: {
  modele: ModeleEnregistre;
  budget: BudgetMemoire;
  onBasculerFavori?: (modele: ModeleEnregistre) => void;
}): ReactElement {
  return (
    <div className="mb-2 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="truncate text-md font-semibold text-text">{modele.fichier ?? modele.depot}</h3>
        <p className="truncate text-2xs text-text-3">{modele.depot}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {onBasculerFavori !== undefined && (
          <button
            type="button"
            onClick={() => onBasculerFavori(modele)}
            aria-pressed={modele.favori}
            title={modele.favori ? 'Retirer des favoris' : 'Mettre en favori'}
            className={cn(
              'rounded-sm p-1 transition-colors duration-fast ease-out',
              'focus-visible:outline-none focus-visible:shadow-[0_0_0_2px_var(--ring)]',
              modele.favori ? 'text-accent' : 'text-text-3 hover:text-text-2',
            )}
          >
            <Etoile marque={modele.favori} />
          </button>
        )}
        <Badge tone="neutral">{modele.format}</Badge>
        <PastilleFaisabilite faisabilite={evaluer(modele.taille_octets, budget)} />
      </div>
    </div>
  );
}

function ActionsModele({
  modele,
  onCharger,
  onOublier,
  onSupprimerDisque,
}: {
  modele: ModeleEnregistre;
  onCharger?: (modele: ModeleEnregistre) => void;
  onOublier: (identifiant: string) => void;
  onSupprimerDisque?: (modele: ModeleEnregistre) => void;
}): ReactElement {
  return (
    <div className="mt-3 flex items-center justify-between gap-2">
      <EtatMetadonnees modele={modele} />
      <div className="flex gap-1.5">
        {/* « Oublier » ne retire que l'entrée du registre : les fichiers restent, et la
            synchronisation suivante réinscrit le modèle. Sans le dire, l'action paraît sans effet.
            La suppression réelle des octets est proposée à côté, avec sa confirmation. */}
        <Button
          size="sm"
          variant="ghost"
          title="Retire du registre sans effacer les fichiers"
          onClick={(): void => onOublier(modele.id)}
        >
          Oublier
        </Button>
        {onSupprimerDisque !== undefined && (
          <Button
            size="sm"
            variant="ghost"
            title="Efface définitivement les fichiers du disque"
            onClick={(): void => onSupprimerDisque(modele)}
          >
            Supprimer
          </Button>
        )}
        {onCharger !== undefined && (
          <Button size="sm" variant="primary" onClick={(): void => onCharger(modele)}>
            Charger
          </Button>
        )}
      </div>
    </div>
  );
}

/*
 * Résultat d'une vérification de cohérence. Aucune incohérence est une information en soi : elle
 * disculpe le fichier, et c'est souvent ce qu'on cherche à savoir quand un chargement a échoué.
 */
function RapportLigne({ rapport }: { rapport: RapportCoherence }): ReactElement {
  if (rapport.incoherences.length === 0) {
    return (
      <p className="mb-2 text-2xs text-text-3">
        Cohérence vérifiée : ce que le fichier déclare correspond à ce qu'il contient.
      </p>
    );
  }
  return (
    <ul className="mb-2 space-y-1">
      {rapport.incoherences.map((incoherence) => (
        <li key={incoherence.code} className="text-2xs leading-relaxed">
          <Badge tone={incoherence.niveau === 'bloquant' ? 'critical' : 'caution'}>{incoherence.niveau}</Badge>{' '}
          <span className="text-text-2">{incoherence.message}</span>
        </li>
      ))}
    </ul>
  );
}

function CarteModele({
  modele,
  budget,
  onCharger,
  onOublier,
  onSupprimerDisque,
  onBasculerFavori,
}: {
  modele: ModeleEnregistre;
  budget: BudgetMemoire;
  onCharger?: (modele: ModeleEnregistre) => void;
  onOublier: (identifiant: string) => void;
  onSupprimerDisque?: (modele: ModeleEnregistre) => void;
  onBasculerFavori?: (modele: ModeleEnregistre) => void;
}): ReactElement {
  // Le rapport n'est demandé QUE sur action : il relit l'en-tête du fichier, ce qui n'a rien à
  // faire dans le rendu d'une liste de douze cartes.
  const [rapport, setRapport] = useState<RapportCoherence | null>(null);
  const verifier = (): Promise<void> =>
    verifierCoherence(modele.id)
      .then(setRapport)
      .catch((cause: unknown) => journal.erreur(`vérification de ${modele.id}`, cause));

  return (
    <MenuContextuel
      entrees={[
        ...(onCharger !== undefined
          ? [{ libelle: 'Charger', onChoisir: (): void => onCharger(modele) }]
          : []),
        ...(onBasculerFavori !== undefined
          ? [{
              libelle: modele.favori ? 'Retirer des favoris' : 'Mettre en favori',
              onChoisir: (): void => onBasculerFavori(modele),
            }]
          : []),
        { libelle: 'Vérifier la cohérence', onChoisir: (): void => void verifier() },
        { libelle: "Copier l'identifiant", onChoisir: (): void => void navigator.clipboard?.writeText(modele.id) },
        { libelle: 'Oublier (garder les fichiers)', onChoisir: (): void => onOublier(modele.id) },
        ...(onSupprimerDisque !== undefined
          ? [{ libelle: 'Supprimer du disque', onChoisir: (): void => onSupprimerDisque(modele), destructive: true }]
          : []),
      ]}
    >
    <Card level="surface">
      <EnTeteModele modele={modele} budget={budget} onBasculerFavori={onBasculerFavori} />
      {rapport !== null && <RapportLigne rapport={rapport} />}
      <dl className="space-y-1">
        <Champ libelle="Taille sur disque">{octetsLisibles(modele.taille_octets)}</Champ>
        <Champ libelle="Quantification">{modele.quantification ?? 'non lue'}</Champ>
        <Champ libelle="Architecture">{modele.architecture ?? 'non lue'}</Champ>
        <Champ libelle="Contexte natif">
          {modele.contexte_max === null ? 'non lu' : `${entier(modele.contexte_max)} tokens`}
        </Champ>
      </dl>
      <ActionsModele
        modele={modele}
        onCharger={onCharger}
        onOublier={onOublier}
        onSupprimerDisque={onSupprimerDisque}
      />
    </Card>
    </MenuContextuel>
  );
}

export interface ModelesLocauxProps {
  etat: EtatModelesLocaux;
  budget: BudgetMemoire;
  /**
   * Le chargement appartient au domaine `inference` : cet écran délègue et ne construit aucun plan.
   * Absent, le bouton n'apparaît pas — mieux vaut pas d'action qu'une action qui ne mène nulle part.
   */
  onCharger?: (modele: ModeleEnregistre) => void;
}

export function ModelesLocaux({ etat, budget, onCharger }: ModelesLocauxProps): ReactElement {
  // L'inventaire du disque vit à côté du registre : il montre ce qui OCCUPE, là où le registre
  // montre ce qui est CHARGEABLE. Un dossier refusé restait sinon invisible et indestructible.
  const disque = useInventaireDisque();

  const supprimerDuDisque = (modele: ModeleEnregistre): void => {
    const dossier = disque.dossiers.find((candidat) => candidat.depot === modele.depot);
    disque.supprimerDossier(dossier?.dossier ?? modele.depot);
    etat.rafraichir();
  };

  if (etat.liste.length === 0 && disque.dossiers.length === 0) {
    return (
      <p className="text-xs text-text-2">
        {etat.chargement ? 'Lecture du registre…' : 'Aucun modèle sur le disque. La recherche est à côté.'}
      </p>
    );
  }
  // Les favoris sont SÉPARÉS, pas seulement triés en tête : sur une bibliothèque d'une douzaine de
  // modèles, un simple ordre différent ne se remarque plus dès qu'on fait défiler.
  const favoris = etat.liste.filter((modele) => modele.favori);
  const autres = etat.liste.filter((modele) => !modele.favori);

  const carte = (modele: ModeleEnregistre): ReactElement => (
    <motion.div key={modele.id} variants={fadeUp} initial="hidden" animate="visible" exit="exit" layout>
      <CarteModele
        modele={modele}
        budget={budget}
        onCharger={onCharger}
        onOublier={etat.oublier}
        onSupprimerDisque={supprimerDuDisque}
        onBasculerFavori={etat.basculerFavori}
      />
    </motion.div>
  );

  return (
    <>
      {favoris.length > 0 && (
        <section className="mb-8">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-3">Favoris</h3>
          <div className="grid gap-3 md:grid-cols-2">
            <AnimatePresence initial={false}>{favoris.map(carte)}</AnimatePresence>
          </div>
        </section>
      )}
      {favoris.length > 0 && autres.length > 0 && (
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-3">Autres modèles</h3>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <AnimatePresence initial={false}>{autres.map(carte)}</AnimatePresence>
      </div>
      {disque.erreur !== null && <p className="mt-3 text-2xs text-critical">{disque.erreur}</p>}
      <DossiersNonInscrits dossiers={disque.dossiers} onSupprimer={disque.supprimerDossier} />
    </>
  );
}
