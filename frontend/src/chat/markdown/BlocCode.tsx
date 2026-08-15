import { useCallback, useMemo, useState } from 'react';
import type { ReactElement } from 'react';
import { Button } from '../../shared/design';
import { journal } from '../api/journal';
import { CLASSE_JETON, colorier } from './coloration';

export interface BlocCodeProps {
  texte: string;
  langage: string;
  /** `false` pendant le streaming : la clôture ``` n'est pas encore arrivée. */
  complet: boolean;
}

const DUREE_CONFIRMATION_MS = 1600;

function useCopie(texte: string): { copie: boolean; copier: () => void } {
  const [copie, setCopie] = useState<boolean>(false);
  const copier = useCallback((): void => {
    // Le presse-papiers est une API externe : elle refuse hors contexte sécurisé ou sans permission.
    navigator.clipboard
      .writeText(texte)
      .then((): void => {
        setCopie(true);
        window.setTimeout((): void => setCopie(false), DUREE_CONFIRMATION_MS);
      })
      .catch((cause: unknown): void => journal.erreur('copie du bloc de code refusée', cause));
  }, [texte]);
  return { copie, copier };
}

export function BlocCode({ texte, langage, complet }: BlocCodeProps): ReactElement {
  const jetons = useMemo(() => colorier(texte, langage), [texte, langage]);
  const { copie, copier } = useCopie(texte);
  return (
    <figure className="my-2 max-w-full overflow-hidden rounded-sm border border-border bg-bg">
      <figcaption className="flex items-center justify-between gap-2 border-b border-border px-2.5 py-1">
        <span className="min-w-0 truncate font-mono text-2xs text-text-3">{langage !== '' ? langage : 'texte'}</span>
        <Button variant="ghost" size="sm" onClick={copier} aria-label="Copier le bloc de code">
          {copie ? 'copié' : 'copier'}
        </Button>
      </figcaption>
      {/* `overscroll-x-contain` : un balayage arrivé au bout du code ne doit pas se propager à
          l'historique du navigateur, dont le geste « retour » part du même bord. */}
      <pre className="overflow-x-auto overscroll-x-contain px-2.5 py-2 font-mono text-xs leading-relaxed">
        <code>
          {jetons.map((jeton, index) => (
            <span key={index} className={CLASSE_JETON[jeton.type]}>
              {jeton.texte}
            </span>
          ))}
        </code>
        {!complet && <span className="ml-0.5 inline-block h-3 w-1.5 animate-eh-pulse bg-accent align-middle" />}
      </pre>
    </figure>
  );
}
