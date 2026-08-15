import { useState } from 'react';
import type { KeyboardEvent, ReactElement } from 'react';
import { Button } from '../../shared/design';
import { SEQUENCES_ARRET } from './definitions';

/*
 * Liste des séquences d'arrêt. Trois décisions, chacune payée d'un piège évité :
 *
 * 1. **Rien n'est rogné.** Une séquence utile finit souvent par une espace ou un saut de ligne
 *    (« \nUtilisateur : ») ; couper les blancs de bord changerait ce que le moteur compare. Les
 *    chaînes sont donc affichées entre guillemets droits, seule façon de voir un blanc de bord.
 * 2. **Rien n'est interprété.** Ce qui est tapé part littéralement dans le JSON : deux caractères
 *    `\` et `n` ne deviennent pas un saut de ligne. C'est écrit sous le champ plutôt que découvert
 *    sur une séquence qui ne déclenche jamais.
 * 3. **Un doublon n'est pas ajouté.** Il ne changerait rien pour le moteur et ferait un patch pour
 *    du bruit ; la chaîne est déjà visible dans la liste, juste au-dessus du champ.
 */

const CLASSE_SAISIE =
  'min-h-[44px] min-w-0 flex-1 rounded-sm border border-border bg-surface-2 px-2 py-1 font-mono '
  + 'text-xs text-text outline-none placeholder:text-text-3 focus:border-border-strong lg:min-h-0';

interface PuceProps {
  readonly valeur: string;
  readonly onRetirer: () => void;
}

function Puce({ valeur, onRetirer }: PuceProps): ReactElement {
  return (
    <li className="flex max-w-full items-center gap-1.5 rounded-xs bg-surface-2 py-0.5 pl-2 pr-1">
      <span className="min-w-0 break-all font-mono text-2xs text-text">{`"${valeur}"`}</span>
      <button
        type="button"
        onClick={onRetirer}
        aria-label={`Retirer la séquence ${valeur}`}
        className="min-h-[44px] min-w-[44px] shrink-0 rounded-xs px-1 text-2xs text-text-3
          transition-colors duration-fast hover:text-critical lg:min-h-0 lg:min-w-0"
      >
        ×
      </button>
    </li>
  );
}

/** Saisie d'une nouvelle séquence : Entrée vaut le bouton, comme partout ailleurs dans l'écran. */
function ChampAjout({ onAjouter }: { onAjouter: (valeur: string) => void }): ReactElement {
  const [saisie, setSaisie] = useState<string>('');
  const valider = (): void => {
    if (saisie !== '') {
      onAjouter(saisie);
    }
    setSaisie('');
  };
  const surTouche = (evenement: KeyboardEvent<HTMLInputElement>): void => {
    if (evenement.key === 'Enter') {
      evenement.preventDefault();
      valider();
    }
  };
  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        value={saisie}
        onChange={(evenement) => setSaisie(evenement.target.value)}
        onKeyDown={surTouche}
        placeholder="Chaîne qui doit interrompre la génération"
        className={CLASSE_SAISIE}
      />
      <Button variant="secondary" size="sm" onClick={valider} disabled={saisie === ''}>
        Ajouter
      </Button>
    </div>
  );
}

export interface SequencesArretProps {
  readonly valeurs: readonly string[];
  readonly onChanger: (valeurs: string[]) => void;
}

function Liste({ valeurs, onChanger }: SequencesArretProps): ReactElement {
  if (valeurs.length === 0) {
    return <p className="text-2xs text-text-3">{SEQUENCES_ARRET.absence}</p>;
  }
  return (
    <ul className="flex flex-wrap gap-1.5">
      {valeurs.map((valeur, index) => (
        <Puce
          key={`${valeur}-${String(index)}`}
          valeur={valeur}
          onRetirer={() => onChanger(valeurs.filter((_, rang) => rang !== index))}
        />
      ))}
    </ul>
  );
}

export function SequencesArret({ valeurs, onChanger }: SequencesArretProps): ReactElement {
  const ajouter = (valeur: string): void => {
    if (valeurs.includes(valeur)) {
      return;
    }
    onChanger([...valeurs, valeur]);
  };
  return (
    <div className="space-y-1.5">
      <span className="block text-xs text-text-2">{SEQUENCES_ARRET.libelle}</span>
      <Liste valeurs={valeurs} onChanger={onChanger} />
      <ChampAjout onAjouter={ajouter} />
      <p className="text-2xs leading-snug text-text-3">
        {SEQUENCES_ARRET.effet} Le texte est pris à la lettre : « \n » vaut deux caractères, pas un
        saut de ligne.
      </p>
    </div>
  );
}
