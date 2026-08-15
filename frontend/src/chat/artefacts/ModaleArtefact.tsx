import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { Modal } from '../../shared/design';
import { chargerTexteFichier } from '../api/fichiers-api';
import { messageErreur } from '../api/client';
import { chargerLimitesBac } from '../api/limites-api';
import { journal } from '../api/journal';
import { BlocCode } from '../markdown/BlocCode';
import type { ArtefactPresente } from './detection';
import { InterrupteurVue, type VueArtefact } from './InterrupteurVue';
import { decrireLangage } from './langage';

interface EtatContenu {
  texte: string;
  chargement: boolean;
  erreur: string | null;
}

/** Contenu textuel du fichier — chargé à l'ouverture, pas avant : une carte fermée ne coûte rien. */
function useContenuFichier(fichierId: string, ouvert: boolean): EtatContenu {
  const [etat, setEtat] = useState<EtatContenu>({ texte: '', chargement: true, erreur: null });
  useEffect((): (() => void) | undefined => {
    if (!ouvert) {
      return undefined;
    }
    const controleur = new AbortController();
    setEtat({ texte: '', chargement: true, erreur: null });
    chargerTexteFichier(fichierId, controleur.signal)
      .then((texte): void => setEtat({ texte, chargement: false, erreur: null }))
      .catch((cause: unknown): void => {
        if (controleur.signal.aborted) {
          return;
        }
        setEtat({ texte: '', chargement: false, erreur: messageErreur(cause) });
      });
    return (): void => controleur.abort();
  }, [fichierId, ouvert]);
  return etat;
}

/** Texte des limites réelles du bac (plan d'exécution, 2.6) — inutile pour une pièce jointe qui
 * n'a jamais traversé le bac confiné : chargé seulement pour un artefact produit par le modèle. */
function useLimitesBac(applicable: boolean, ouvert: boolean): string {
  const [texte, setTexte] = useState<string>('');
  useEffect((): (() => void) | undefined => {
    if (!applicable || !ouvert) {
      return undefined;
    }
    const controleur = new AbortController();
    chargerLimitesBac(controleur.signal)
      .then(setTexte)
      .catch((cause: unknown): void => {
        if (!controleur.signal.aborted) {
          journal.avertissement('texte des limites du bac indisponible', cause);
        }
      });
    return (): void => controleur.abort();
  }, [applicable, ouvert]);
  return texte;
}

function CorpsCode({ etat, langage }: { etat: EtatContenu; langage: string }): ReactElement {
  if (etat.chargement) {
    return <p className="text-xs text-text-3">Chargement…</p>;
  }
  if (etat.erreur !== null) {
    return <p className="text-xs text-critical">{etat.erreur}</p>;
  }
  return <BlocCode texte={etat.texte} langage={langage} complet />;
}

function CorpsApercu({ etat }: { etat: EtatContenu }): ReactElement {
  if (etat.chargement) {
    return <p className="text-xs text-text-3">Chargement…</p>;
  }
  if (etat.erreur !== null) {
    return <p className="text-xs text-critical">{etat.erreur}</p>;
  }
  return (
    <iframe
      title="Aperçu du fichier HTML"
      // Contenu produit par un modèle = contenu NON FIABLE (plan d'exécution, 2.6). `sandbox` SANS
      // `allow-same-origin` place ce document dans une origine opaque distincte de l'application :
      // aucun accès à `document.cookie`, au stockage local, ni à rien de ce que sert ce frontend —
      // même avec `allow-scripts`, qui n'autorise que l'exécution, pas l'accès à l'origine réelle.
      sandbox="allow-scripts"
      srcDoc={etat.texte}
      data-testid="apercu-html"
      // `dvh` et non `vh` : sous la barre d'URL escamotable, 60vh dépasse ce qui est réellement visible.
      className="h-[60dvh] w-full rounded-sm border border-border bg-white"
    />
  );
}

function NoteLimites({ texte }: { texte: string }): ReactElement | null {
  if (texte === '') {
    return null;
  }
  return (
    <p className="mt-3 border-t border-border pt-3 text-2xs leading-relaxed text-text-3" data-testid="limites-bac">
      {texte}
    </p>
  );
}

export interface ModaleArtefactProps {
  artefact: ArtefactPresente;
  ouvert: boolean;
  onFermer: () => void;
}

/**
 * Fenêtre d'un artefact — agrandissable (`Modal` `expansible`), interrupteur code/aperçu à deux
 * icônes dans l'en-tête, note sur les limites réelles du bac pour un fichier produit par le modèle.
 */
export function ModaleArtefact({ artefact, ouvert, onFermer }: ModaleArtefactProps): ReactElement {
  const [vue, setVue] = useState<VueArtefact>('code');
  const { langage, apercuPossible, raisonAbsenceApercu } = decrireLangage(artefact.nom_affiche, artefact.type_mime);
  const contenu = useContenuFichier(artefact.fichier_id, ouvert);
  const limites = useLimitesBac(artefact.origine === 'modele', ouvert);

  // Un artefact sans aperçu ne doit jamais rester bloqué sur une vue qu'il ne peut plus servir —
  // arrive si cette instance montée présente successivement des fichiers de langages différents.
  useEffect((): void => {
    if (!apercuPossible && vue === 'apercu') {
      setVue('code');
    }
  }, [apercuPossible, vue]);

  return (
    <Modal
      open={ouvert}
      onClose={onFermer}
      title={artefact.nom_affiche}
      size="lg"
      expansible
      actionsEntete={
        <InterrupteurVue
          vue={vue}
          onChanger={setVue}
          apercuPossible={apercuPossible}
          raisonAbsenceApercu={raisonAbsenceApercu}
        />
      }
    >
      {vue === 'code' ? <CorpsCode etat={contenu} langage={langage} /> : <CorpsApercu etat={contenu} />}
      <NoteLimites texte={limites} />
    </Modal>
  );
}
