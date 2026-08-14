import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChangeEvent, KeyboardEvent, ReactElement, RefObject } from 'react';
import { Button } from '../../shared/design';

/*
 * Saisie du message. Entrée envoie, Maj+Entrée passe à la ligne — la convention des interfaces de
 * chat, et la seule qui ne surprenne personne.
 *
 * Pendant une génération, le bouton devient « Arrêter » plutôt que de disparaître : l'annulation
 * doit être atteignable là où le regard est déjà, sans chercher un contrôle ailleurs dans l'écran.
 */

const HAUTEUR_MAX_PX = 200;

const CLASSE_CADRE =
  'flex items-end gap-2 rounded-md border border-border bg-surface px-3 py-2 ' +
  'focus-within:border-border-strong';

function useHauteurAuto(valeur: string): RefObject<HTMLTextAreaElement> {
  const zone = useRef<HTMLTextAreaElement>(null);
  useEffect((): void => {
    const element = zone.current;
    if (element === null) {
      return;
    }
    // Remise à zéro avant mesure : sans elle, `scrollHeight` ne redescend jamais.
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, HAUTEUR_MAX_PX)}px`;
  }, [valeur]);
  return zone;
}

interface BarreSaisieProps {
  texte: string;
  genere: boolean;
  desactive: boolean;
  zone: RefObject<HTMLTextAreaElement>;
  onTexte: (evenement: ChangeEvent<HTMLTextAreaElement>) => void;
  onTouche: (evenement: KeyboardEvent<HTMLTextAreaElement>) => void;
  onEnvoyer: () => void;
  onAnnuler: () => void;
}

function BarreSaisie(props: BarreSaisieProps): ReactElement {
  const { texte, genere, desactive, zone, onTexte, onTouche, onEnvoyer, onAnnuler } = props;
  return (
    <div className={CLASSE_CADRE}>
      <textarea
        ref={zone}
        rows={1}
        value={texte}
        disabled={desactive}
        onChange={onTexte}
        onKeyDown={onTouche}
        placeholder="Écrire un message…"
        className="flex-1 resize-none bg-transparent text-sm text-text outline-none placeholder:text-text-3"
      />
      {genere ? (
        <Button variant="secondary" size="sm" onClick={onAnnuler}>
          Arrêter
        </Button>
      ) : (
        <Button variant="primary" size="sm" onClick={onEnvoyer} disabled={desactive || texte.trim() === ''}>
          Envoyer
        </Button>
      )}
    </div>
  );
}

export interface ComposeurProps {
  genere: boolean;
  desactive: boolean;
  /** Raison de l'indisponibilité, affichée sous la zone de saisie. Vide quand tout est prêt. */
  empechement: string;
  onEnvoyer: (contenu: string) => void;
  onAnnuler: () => void;
}

export function Composeur({
  genere,
  desactive,
  empechement,
  onEnvoyer,
  onAnnuler,
}: ComposeurProps): ReactElement {
  const [texte, setTexte] = useState<string>('');
  const zone = useHauteurAuto(texte);

  const envoyer = useCallback((): void => {
    const contenu = texte.trim();
    if (contenu === '' || genere || desactive) {
      return;
    }
    onEnvoyer(contenu);
    setTexte('');
  }, [texte, genere, desactive, onEnvoyer]);

  const surTouche = (evenement: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (evenement.key === 'Enter' && !evenement.shiftKey) {
      evenement.preventDefault();
      envoyer();
    }
  };

  return (
    <div className="border-t border-border px-6 py-4">
      <div className="mx-auto max-w-3xl">
        <BarreSaisie
          texte={texte}
          genere={genere}
          desactive={desactive}
          zone={zone}
          onTexte={(evenement) => setTexte(evenement.target.value)}
          onTouche={surTouche}
          onEnvoyer={envoyer}
          onAnnuler={onAnnuler}
        />
        {empechement !== '' && <p className="mt-1.5 text-2xs text-text-3">{empechement}</p>}
      </div>
    </div>
  );
}
