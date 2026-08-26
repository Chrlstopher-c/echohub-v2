/*
 * Pièces jointes du composeur — icônes, boutons déclencheurs, rangée d'état et dépôt immédiat.
 *
 * Sorti de `Composeur.tsx` quand la refonte l'a fait passer la limite de 500 lignes : tout ce qui
 * touche aux pièces change ensemble (règle de l'opérateur sur le dépôt immédiat, remplacement des
 * emoji par des icônes au trait), et rien d'autre dans le composeur n'y touche.
 */

import { useCallback, useState } from 'react';
import type { ChangeEvent, ReactElement, ReactNode, RefObject } from 'react';
import { cn } from '../../shared/design';
import { deposerFichier } from '../api/fichiers-api';
import { messageErreur } from '../api/client';
import { journal } from '../api/journal';
import type { FichierConversation } from '../api/contrats';

const CLASSE_BOUTON_PIECE =
  'flex shrink-0 items-center justify-center rounded text-text-3 ' +
  'min-h-[44px] min-w-[44px] hover:bg-surface-2 hover:text-text disabled:opacity-40 ' +
  'lg:min-h-0 lg:min-w-0 lg:px-1.5 lg:py-1';

/*
 * Icônes monochromes au trait 1,5 px, comme partout ailleurs dans l'application (DESIGN.md). Les
 * emoji posés au premier jet (📎, 📷) rendaient en couleur et changeaient de dessin d'une
 * plateforme à l'autre : c'était le seul endroit où une icône n'était pas dessinée par le projet.
 */
const TRAIT_PIECE = {
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const;

const CHEMIN_TROMBONE =
  'M10.5 4.5 5.9 9.1a1.7 1.7 0 0 0 2.4 2.4l4.6-4.6a3.1 3.1 0 0 0-4.4-4.4' +
  'L3.6 7.4a4.5 4.5 0 0 0 6.4 6.4l3.4-3.4';

export function IconeTrombone(): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden="true">
      <path d={CHEMIN_TROMBONE} {...TRAIT_PIECE} />
    </svg>
  );
}

export function IconeAppareilPhoto(): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden="true">
      <path d="M2 5.5h2.2l1-1.5h3.6l1 1.5H14v7H2z" {...TRAIT_PIECE} />
      <circle cx="8" cy="9" r="2.2" {...TRAIT_PIECE} />
    </svg>
  );
}

export function BoutonPiece({
  libelle,
  desactive,
  onClic,
  className,
  children,
}: {
  libelle: string;
  desactive: boolean;
  onClic: () => void;
  className?: string;
  children: ReactNode;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={onClic}
      disabled={desactive}
      aria-label={libelle}
      title={libelle}
      className={cn(CLASSE_BOUTON_PIECE, className)}
    >
      {children}
    </button>
  );
}



const CLASSE_PIECE =
  'flex items-center gap-1.5 rounded-full border border-border bg-surface-2 px-2.5 py-1 ' +
  'text-2xs text-text-2';

/** Pièce en cours de dépôt ou déjà déposée — l'identifiant local suit son sort avant l'identifiant serveur. */
export interface PieceComposeur {
  cle: string;
  nom: string;
  enCours: boolean;
  fichier: FichierConversation | null;
  erreur: string | null;
}

export function RangeePieces({
  pieces,
  onRetirer,
}: {
  pieces: PieceComposeur[];
  onRetirer: (cle: string) => void;
}): ReactElement | null {
  if (pieces.length === 0) {
    return null;
  }
  return (
    <div className="mb-2 flex flex-wrap gap-1.5" data-testid="pieces-jointes">
      {pieces.map((piece) => (
        <span
          key={piece.cle}
          data-testid="piece-jointe"
          className={CLASSE_PIECE}
        >
          <span className="max-w-[10rem] truncate">
            {piece.enCours ? `Envoi de ${piece.nom}…` : piece.erreur !== null ? `${piece.nom} (échec)` : piece.nom}
          </span>
          <button
            type="button"
            onClick={() => onRetirer(piece.cle)}
            className="min-h-[44px] min-w-[44px] text-text-3 hover:text-text lg:min-h-0 lg:min-w-0"
            aria-label={`Retirer ${piece.nom}`}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  );
}



/*
 * Les deux entrées de fichier, jamais visibles : ce sont les boutons qui les déclenchent.
 * `capture="environment"` ouvre l'appareil photo arrière ; sans matériel de capture, le navigateur
 * retombe de lui-même sur le sélecteur habituel — donc jamais de chemin mort.
 */
export function EntreesFichier({
  fichier,
  photo,
  onChoisir,
}: {
  fichier: RefObject<HTMLInputElement>;
  photo: RefObject<HTMLInputElement>;
  onChoisir: (evenement: ChangeEvent<HTMLInputElement>) => void;
}): ReactElement {
  return (
    <>
      <input ref={fichier} type="file" multiple className="hidden" onChange={onChoisir} data-testid="entree-fichier" />
      <input
        ref={photo}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={onChoisir}
        data-testid="entree-photo"
      />
    </>
  );
}



function cleLocale(): string {
  return `piece-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Dépose immédiatement chaque fichier choisi (collage, glisser-déposer, sélection) dans le magasin. */
export function useDepotPieces(
  conversationId: string | null,
): [PieceComposeur[], (fichiers: File[]) => void, (cle: string) => void, () => void] {
  const [pieces, setPieces] = useState<PieceComposeur[]>([]);

  const deposer = useCallback(
    (fichiers: File[]): void => {
      if (conversationId === null || fichiers.length === 0) {
        return;
      }
      for (const fichier of fichiers) {
        const cle = cleLocale();
        setPieces((courant) => [...courant, { cle, nom: fichier.name, enCours: true, fichier: null, erreur: null }]);
        deposerFichier(conversationId, fichier)
          .then((depose): void => {
            setPieces((courant) =>
              courant.map((p) => (p.cle === cle ? { ...p, enCours: false, fichier: depose } : p)),
            );
          })
          .catch((cause: unknown): void => {
            journal.erreur('dépôt de la pièce jointe refusé', cause);
            setPieces((courant) =>
              courant.map((p) => (p.cle === cle ? { ...p, enCours: false, erreur: messageErreur(cause) } : p)),
            );
          });
      }
    },
    [conversationId],
  );

  const retirer = useCallback((cle: string): void => {
    setPieces((courant) => courant.filter((p) => p.cle !== cle));
  }, []);

  const vider = useCallback((): void => setPieces([]), []);

  return [pieces, deposer, retirer, vider];
}
