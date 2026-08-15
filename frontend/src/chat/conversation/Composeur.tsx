import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  ChangeEvent,
  ClipboardEvent,
  DragEvent,
  KeyboardEvent,
  ReactElement,
  RefObject,
} from 'react';
import { Button } from '../../shared/design';
import { deposerFichier } from '../api/fichiers-api';
import { messageErreur } from '../api/client';
import { journal } from '../api/journal';
import type { FichierConversation } from '../api/contrats';

/*
 * Saisie du message. Entrée envoie, Maj+Entrée passe à la ligne — la convention des interfaces de
 * chat, et la seule qui ne surprenne personne.
 *
 * Pendant une génération, le bouton devient « Arrêter » plutôt que de disparaître : l'annulation
 * doit être atteignable là où le regard est déjà, sans chercher un contrôle ailleurs dans l'écran.
 *
 * PIÈCES JOINTES — règle de l'opérateur (plan d'exécution, 2.4) : le composeur accepte une image
 * (collage, glisser-déposer, sélection) ou un fichier quelconque QUEL QUE SOIT le modèle chargé, y
 * compris si aucun n'est chargé. Il ne bloque jamais l'envoi et n'affiche jamais de message du type
 * « ce modèle ne prend pas en charge les images » — c'est au modèle chargé de répondre, avec ses
 * mots, s'il ne voit rien. Chaque pièce est déposée dans le magasin dès qu'elle est choisie ; seul
 * son identifiant part avec le message.
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

/** Pièce en cours de dépôt ou déjà déposée — l'identifiant local suit son sort avant l'identifiant serveur. */
interface PieceComposeur {
  cle: string;
  nom: string;
  enCours: boolean;
  fichier: FichierConversation | null;
  erreur: string | null;
}

function RangeePieces({
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
          className="flex items-center gap-1.5 rounded-full border border-border bg-surface-2 px-2.5 py-1 text-2xs text-text-2"
        >
          <span className="max-w-[10rem] truncate">
            {piece.enCours ? `Envoi de ${piece.nom}…` : piece.erreur !== null ? `${piece.nom} (échec)` : piece.nom}
          </span>
          <button
            type="button"
            onClick={() => onRetirer(piece.cle)}
            className="text-text-3 hover:text-text"
            aria-label={`Retirer ${piece.nom}`}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  );
}

interface BarreSaisieProps {
  texte: string;
  genere: boolean;
  desactive: boolean;
  zone: RefObject<HTMLTextAreaElement>;
  onTexte: (evenement: ChangeEvent<HTMLTextAreaElement>) => void;
  onTouche: (evenement: KeyboardEvent<HTMLTextAreaElement>) => void;
  onColle: (evenement: ClipboardEvent<HTMLTextAreaElement>) => void;
  onEnvoyer: () => void;
  onAnnuler: () => void;
  onChoisirFichier: () => void;
}

function BarreSaisie(props: BarreSaisieProps): ReactElement {
  const { texte, genere, desactive, zone, onTexte, onTouche, onColle, onEnvoyer, onAnnuler, onChoisirFichier } =
    props;
  return (
    <div className={CLASSE_CADRE}>
      <button
        type="button"
        onClick={onChoisirFichier}
        disabled={desactive}
        aria-label="Joindre un fichier"
        title="Joindre un fichier"
        className="shrink-0 rounded px-1.5 py-1 text-text-3 hover:bg-surface-2 hover:text-text disabled:opacity-40"
      >
        📎
      </button>
      <textarea
        ref={zone}
        rows={1}
        value={texte}
        disabled={desactive}
        onChange={onTexte}
        onKeyDown={onTouche}
        onPaste={onColle}
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
  /** Conversation courante — nécessaire pour déposer une pièce jointe dans le bon dossier. */
  conversationId: string | null;
  onEnvoyer: (contenu: string, fichierIds: string[]) => void;
  onAnnuler: () => void;
}

function cleLocale(): string {
  return `piece-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Dépose immédiatement chaque fichier choisi (collage, glisser-déposer, sélection) dans le magasin. */
function useDepotPieces(
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

export function Composeur({
  genere,
  desactive,
  empechement,
  conversationId,
  onEnvoyer,
  onAnnuler,
}: ComposeurProps): ReactElement {
  const [texte, setTexte] = useState<string>('');
  const zone = useHauteurAuto(texte);
  const entreeFichier = useRef<HTMLInputElement>(null);
  const [pieces, deposer, retirer, vider] = useDepotPieces(conversationId);

  const envoyer = useCallback((): void => {
    const contenu = texte.trim();
    if (contenu === '' || genere || desactive) {
      return;
    }
    // Les pièces encore en cours de dépôt sont exclues plutôt que d'attendre : le texte part sans
    // délai, et une pièce arrivée trop tard reste simplement une pièce que ce message n'aura pas.
    const fichierIds = pieces.filter((p) => p.fichier !== null).map((p) => (p.fichier as FichierConversation).id);
    onEnvoyer(contenu, fichierIds);
    setTexte('');
    vider();
  }, [texte, genere, desactive, pieces, onEnvoyer, vider]);

  const surTouche = (evenement: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (evenement.key === 'Enter' && !evenement.shiftKey) {
      evenement.preventDefault();
      envoyer();
    }
  };

  const surCollage = (evenement: ClipboardEvent<HTMLTextAreaElement>): void => {
    const fichiers = Array.from(evenement.clipboardData?.files ?? []);
    if (fichiers.length === 0) {
      return;
    }
    evenement.preventDefault();
    deposer(fichiers);
  };

  const surDepot = (evenement: DragEvent<HTMLDivElement>): void => {
    evenement.preventDefault();
    deposer(Array.from(evenement.dataTransfer.files));
  };

  const surSelectionFichier = (evenement: ChangeEvent<HTMLInputElement>): void => {
    deposer(Array.from(evenement.target.files ?? []));
    evenement.target.value = '';
  };

  return (
    <div
      className="border-t border-border px-6 py-4"
      onDragOver={(evenement) => evenement.preventDefault()}
      onDrop={surDepot}
    >
      <div className="mx-auto max-w-3xl">
        <input
          ref={entreeFichier}
          type="file"
          multiple
          className="hidden"
          onChange={surSelectionFichier}
          data-testid="entree-fichier"
        />
        <RangeePieces pieces={pieces} onRetirer={retirer} />
        <BarreSaisie
          texte={texte}
          genere={genere}
          desactive={desactive}
          zone={zone}
          onTexte={(evenement) => setTexte(evenement.target.value)}
          onTouche={surTouche}
          onColle={surCollage}
          onEnvoyer={envoyer}
          onAnnuler={onAnnuler}
          onChoisirFichier={() => entreeFichier.current?.click()}
        />
        {empechement !== '' && <p className="mt-1.5 text-2xs text-text-3">{empechement}</p>}
      </div>
    </div>
  );
}
