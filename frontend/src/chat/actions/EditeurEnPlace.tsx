/*
 * Modification d'un message utilisateur, à la place du message.
 *
 * En place et non dans le composeur : ce qu'on modifie est un tour situé dans l'histoire, pas un
 * nouveau tour. L'éditer depuis le bas de l'écran ferait perdre le contexte de ce à quoi il répond.
 *
 * L'envoi crée une branche SŒUR : le texte d'origine et la réponse qu'il avait obtenue restent
 * entiers, atteignables par les flèches de variantes. La phrase sous la zone de saisie le dit — une
 * action qui semble écraser doit prouver qu'elle n'écrase pas, sinon elle sera évitée.
 */

import { useState } from 'react';
import type { KeyboardEvent, ReactElement } from 'react';
import { Button } from '../../shared/design';

/* Bornes de hauteur : assez pour relire un paragraphe, pas au point de pousser le fil hors champ. */
const LIGNES_MIN = 2;
const LIGNES_MAX = 14;

const MOTIF_OCCUPE = 'Une génération est en cours';

/*
 * `min-w` : la bulle utilisateur se dimensionne sur son contenu ; sans plancher, modifier un
 * message d'un mot donnerait une zone de saisie de la largeur de ce mot.
 */
const CLASSE_ZONE =
  'w-full resize-y rounded-sm border border-border-strong bg-surface px-2 py-1.5 ' +
  'text-sm text-text outline-none focus:shadow-[0_0_0_3px_var(--ring)]';

function lignesUtiles(contenu: string): number {
  return Math.min(LIGNES_MAX, Math.max(LIGNES_MIN, contenu.split('\n').length));
}

interface Touches {
  contenu: string;
  envoyable: boolean;
  onAnnuler: () => void;
  onConfirmer: (contenu: string) => void;
}

/*
 * Même convention que le composeur : Entrée envoie, Maj+Entrée passe à la ligne, Échap abandonne.
 * Deux conventions différentes dans le même écran feraient perdre un texte au premier réflexe.
 */
function surTouche(evenement: KeyboardEvent<HTMLTextAreaElement>, touches: Touches): void {
  if (evenement.key === 'Escape') {
    evenement.preventDefault();
    touches.onAnnuler();
    return;
  }
  if (evenement.key === 'Enter' && !evenement.shiftKey && touches.envoyable) {
    evenement.preventDefault();
    touches.onConfirmer(touches.contenu);
  }
}

interface PiedProps {
  envoyable: boolean;
  occupe: boolean;
  onAnnuler: () => void;
  onConfirmer: () => void;
}

function PiedEdition({ envoyable, occupe, onAnnuler, onConfirmer }: PiedProps): ReactElement {
  return (
    <div className="mt-1.5 flex items-center justify-between gap-3">
      <p className="text-2xs text-text-3">
        Le message d’origine et sa réponse sont conservés, atteignables par « ‹ › ».
      </p>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button variant="ghost" size="sm" onClick={onAnnuler}>
          Annuler
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={!envoyable}
          title={occupe ? MOTIF_OCCUPE : undefined}
          onClick={onConfirmer}
        >
          Envoyer dans une variante
        </Button>
      </div>
    </div>
  );
}

export interface EditeurEnPlaceProps {
  contenuInitial: string;
  /** Génération en cours : l'envoi serait refusé par le backend, le bouton le dit avant le clic. */
  occupe: boolean;
  onAnnuler: () => void;
  onConfirmer: (contenu: string) => void;
}

export function EditeurEnPlace({
  contenuInitial,
  occupe,
  onAnnuler,
  onConfirmer,
}: EditeurEnPlaceProps): ReactElement {
  const [texte, setTexte] = useState<string>(contenuInitial);
  const contenu = texte.trim();
  const envoyable = contenu !== '' && !occupe;
  const touches: Touches = { contenu, envoyable, onAnnuler, onConfirmer };

  return (
    <div className="w-full min-w-[16rem]">
      <textarea
        autoFocus
        rows={lignesUtiles(contenuInitial)}
        value={texte}
        onChange={(evenement) => setTexte(evenement.target.value)}
        onKeyDown={(evenement) => surTouche(evenement, touches)}
        aria-label="Modifier ce message"
        className={CLASSE_ZONE}
      />
      <PiedEdition
        envoyable={envoyable}
        occupe={occupe}
        onAnnuler={onAnnuler}
        onConfirmer={() => onConfirmer(contenu)}
      />
    </div>
  );
}
