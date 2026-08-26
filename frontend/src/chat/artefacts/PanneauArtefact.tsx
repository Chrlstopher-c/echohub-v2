/*
 * L'atelier : le panneau où un artefact créé par le modèle se regarde et se manipule.
 *
 * Sur grand écran il prend la place du plan de chargement dans la colonne de droite — le plan dit
 * l'état de la machine, l'artefact est ce qu'on est en train de regarder ; les deux répondent à
 * des moments différents et ne se disputent pas la même colonne. Sous le seuil, l'écran de chat le
 * monte dans une `Feuille`. Le panneau lui-même ne connaît ni la colonne ni le tiroir.
 *
 * L'aperçu est la vue par défaut quand le type s'y prête : l'objet de l'outil est de MONTRER, la
 * source reste à un geste. Le sélecteur de versions est un compteur ‹ v 2/3 › — chaque correction
 * du modèle reste consultable, et revenir en arrière est un mouvement, pas une fouille.
 */

import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { Badge, Button, cn, Modal } from '../../shared/design';
import { messageErreur } from '../api/client';
import { chargerTexteFichier } from '../api/fichiers-api';
import type { VersionArtefact } from './detection';
import type { ArtefactCatalogue } from './versions';
import { apercuPossible, VueArtefact, type VueAtelier } from './VueArtefact';

export type ChargeurContenu = (fichierId: string, signal: AbortSignal) => Promise<string>;

interface EtatContenu {
  texte: string;
  chargement: boolean;
  erreur: string | null;
}

/** Contenu de LA version affichée — rechargé quand on change de version, jamais avant l'ouverture. */
function useContenuVersion(fichierId: string, charger: ChargeurContenu): EtatContenu {
  const [etat, setEtat] = useState<EtatContenu>({ texte: '', chargement: true, erreur: null });
  useEffect((): (() => void) => {
    const controleur = new AbortController();
    setEtat({ texte: '', chargement: true, erreur: null });
    charger(fichierId, controleur.signal)
      .then((texte): void => setEtat({ texte, chargement: false, erreur: null }))
      .catch((cause: unknown): void => {
        if (!controleur.signal.aborted) {
          setEtat({ texte: '', chargement: false, erreur: messageErreur(cause) });
        }
      });
    return (): void => controleur.abort();
  }, [fichierId, charger]);
  return etat;
}

function chargerParApi(fichierId: string, signal: AbortSignal): Promise<string> {
  return chargerTexteFichier(fichierId, signal);
}

interface SelecteurVersionProps {
  versions: readonly VersionArtefact[];
  courante: VersionArtefact;
  onChoisir: (numero: number) => void;
}

function FlecheVersion({
  sens,
  voisine,
  onChoisir,
}: {
  sens: 'precedente' | 'suivante';
  voisine: VersionArtefact | undefined;
  onChoisir: (numero: number) => void;
}): ReactElement {
  return (
    <button
      type="button"
      className={cn(
        'flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xs text-text-2',
        'transition-colors duration-fast hover:bg-surface-2 hover:text-text disabled:opacity-40',
        'disabled:hover:bg-transparent lg:min-h-0 lg:min-w-0 lg:h-6 lg:w-6',
      )}
      disabled={voisine === undefined}
      aria-label={sens === 'precedente' ? 'Version précédente' : 'Version suivante'}
      onClick={() => voisine !== undefined && onChoisir(voisine.version)}
    >
      {sens === 'precedente' ? '‹' : '›'}
    </button>
  );
}

function SelecteurVersion({ versions, courante, onChoisir }: SelecteurVersionProps): ReactElement | null {
  // Une seule version : pas de sélecteur. Un compteur « v 1/1 » annoncerait une navigation qui
  // n'existe pas — le numéro seul vit déjà sur la carte du fil.
  if (versions.length < 2) {
    return null;
  }
  const index = versions.findIndex((v) => v.version === courante.version);
  return (
    <span className="flex items-center gap-0.5" data-testid="selecteur-version">
      <FlecheVersion sens="precedente" voisine={versions[index - 1]} onChoisir={onChoisir} />
      <span className="font-mono text-2xs tabular-nums text-text-2">
        v {index + 1}/{versions.length}
      </span>
      <FlecheVersion sens="suivante" voisine={versions[index + 1]} onChoisir={onChoisir} />
    </span>
  );
}

function InterrupteurVueAtelier({
  vue,
  possible,
  onChanger,
}: {
  vue: VueAtelier;
  possible: boolean;
  onChanger: (vue: VueAtelier) => void;
}): ReactElement | null {
  if (!possible) {
    return null;
  }
  const classe = (active: boolean): string =>
    cn(
      'rounded-xs px-1.5 py-0.5 text-2xs transition-colors duration-fast',
      active ? 'bg-surface-2 text-text' : 'text-text-3 hover:text-text-2',
    );
  return (
    <span className="flex items-center gap-0.5 rounded-sm border border-border p-0.5">
      <button type="button" aria-pressed={vue === 'apercu'} className={classe(vue === 'apercu')}
        onClick={() => onChanger('apercu')}>
        aperçu
      </button>
      <button type="button" aria-pressed={vue === 'code'} className={classe(vue === 'code')}
        onClick={() => onChanger('code')}>
        code
      </button>
    </span>
  );
}

interface EnTetePanneauProps {
  artefact: ArtefactCatalogue;
  version: VersionArtefact;
  vue: VueAtelier;
  onChoisirVersion: (numero: number) => void;
  onChangerVue: (vue: VueAtelier) => void;
  onAgrandir: () => void;
  onFermer: () => void;
}

function EnTetePanneau(props: EnTetePanneauProps): ReactElement {
  const { artefact, version, vue } = props;
  return (
    <>
      <header className="flex shrink-0 items-center gap-2 px-3 pt-2.5">
        <h2 className="min-w-0 flex-1 truncate text-md font-semibold text-text" title={artefact.titre}>
          {artefact.titre}
        </h2>
        <Button variant="ghost" size="sm" onClick={props.onFermer} aria-label="Fermer l’artefact">
          fermer
        </Button>
      </header>
      <div className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 px-3 pb-2 pt-1">
        <Badge tone="neutral">{artefact.type}</Badge>
        <SelecteurVersion versions={artefact.versions} courante={version} onChoisir={props.onChoisirVersion} />
        <span className="ml-auto flex items-center gap-2">
          <InterrupteurVueAtelier vue={vue} possible={apercuPossible(artefact.type)} onChanger={props.onChangerVue} />
          <Button variant="ghost" size="sm" onClick={props.onAgrandir}>
            agrandir
          </Button>
        </span>
      </div>
    </>
  );
}

function Corps({ etat, version, vue }: { etat: EtatContenu; version: VersionArtefact; vue: VueAtelier }):
  ReactElement {
  if (etat.chargement) {
    return <p className="px-3 py-2 text-xs text-text-3">Chargement…</p>;
  }
  if (etat.erreur !== null) {
    return <p className="px-3 py-2 text-xs text-critical">{etat.erreur}</p>;
  }
  return <VueArtefact version={version} contenu={etat.texte} vue={vue} />;
}

export interface PanneauArtefactProps {
  readonly artefact: ArtefactCatalogue;
  readonly version: VersionArtefact;
  readonly onChoisirVersion: (numero: number) => void;
  readonly onFermer: () => void;
  /** Injectable pour la page de démonstration et les captures ; l'API réelle par défaut. */
  readonly chargerContenu?: ChargeurContenu;
}

export function PanneauArtefact({
  artefact,
  version,
  onChoisirVersion,
  onFermer,
  chargerContenu,
}: PanneauArtefactProps): ReactElement {
  // Aperçu d'abord quand il existe : montrer est l'objet de l'outil. La préférence suit le TYPE,
  // pas la version — corriger une page ne doit pas la faire retomber en vue code.
  const [vue, setVue] = useState<VueAtelier>(apercuPossible(artefact.type) ? 'apercu' : 'code');
  const [agrandi, setAgrandi] = useState<boolean>(false);
  const etat = useContenuVersion(version.fichier_id, chargerContenu ?? chargerParApi);
  return (
    <section className="flex h-full min-h-0 flex-col rounded-md border border-border bg-surface">
      <EnTetePanneau
        artefact={artefact}
        version={version}
        vue={vue}
        onChoisirVersion={onChoisirVersion}
        onChangerVue={setVue}
        onAgrandir={() => setAgrandi(true)}
        onFermer={onFermer}
      />
      <div className="min-h-0 flex-1 border-t border-border">
        <Corps etat={etat} version={version} vue={vue} />
      </div>
      <Modal open={agrandi} onClose={() => setAgrandi(false)} title={artefact.titre} size="lg" expansible>
        {/* Même contenu, même vue : la modale n'est qu'un agrandissement, pas un autre rendu. */}
        <div className="h-[70dvh]">
          <Corps etat={etat} version={version} vue={vue} />
        </div>
      </Modal>
    </section>
  );
}
