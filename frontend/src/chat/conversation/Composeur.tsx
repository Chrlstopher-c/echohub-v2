import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  ChangeEvent,
  ClipboardEvent,
  DragEvent,
  KeyboardEvent,
  ReactElement,
  ReactNode,
  RefObject,
} from 'react';
import { Button, cn } from '../../shared/design';
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
 *
 * AU DOIGT : le collage et le glisser-déposer n'existent pas sur un téléphone. Deux déclencheurs
 * explicites les remplacent — « Joindre un fichier » (sélecteur), et « Prendre une photo »
 * (`capture` sur une entrée image, donc l'appareil photo directement). Le second n'est proposé que
 * sous 1024 px, où il a un sens. Aucun des deux ne juge le modèle chargé : la règle de l'opérateur
 * tient, l'application transmet toujours et ne refuse jamais d'elle-même.
 */

const HAUTEUR_MAX_PX = 200;

/*
 * Sous le seuil, la rangée passe à DEUX lignes : la saisie occupe la sienne, les boutons suivent.
 * Sur une seule ligne à 375 px, les trois boutons consommaient 156 px des 351 disponibles et ne
 * laissaient que 165 px pour écrire — mesuré le 2026-08-15, soit une vingtaine de caractères
 * visibles. Au-dessus du seuil, `lg:flex-nowrap` restaure la rangée unique.
 */
const CLASSE_CADRE =
  'flex flex-wrap items-end gap-1 rounded-md border border-border bg-surface px-2 py-1.5 ' +
  'focus-within:border-border-strong lg:flex-nowrap lg:gap-2 lg:px-3 lg:py-2';

/* `py-2.5` au doigt : la zone de saisie elle-même doit faire 44 px de haut à une ligne.
   `order-first basis-full` la place seule sur la première ligne tant qu'on est sous le seuil. */
const CLASSE_ZONE_SAISIE =
  'order-first w-full min-w-0 basis-full resize-none bg-transparent py-2.5 text-sm text-text ' +
  'outline-none placeholder:text-text-3 lg:order-none lg:w-auto lg:flex-1 lg:basis-auto lg:py-0';

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

function IconeTrombone(): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden="true">
      <path d={CHEMIN_TROMBONE} {...TRAIT_PIECE} />
    </svg>
  );
}

function IconeAppareilPhoto(): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden="true">
      <path d="M2 5.5h2.2l1-1.5h3.6l1 1.5H14v7H2z" {...TRAIT_PIECE} />
      <circle cx="8" cy="9" r="2.2" {...TRAIT_PIECE} />
    </svg>
  );
}

function BoutonPiece({
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

const CLASSE_PIECE =
  'flex items-center gap-1.5 rounded-full border border-border bg-surface-2 px-2.5 py-1 ' +
  'text-2xs text-text-2';

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
  onPrendrePhoto: () => void;
}

/*
 * Les deux entrées de fichier, jamais visibles : ce sont les boutons qui les déclenchent.
 * `capture="environment"` ouvre l'appareil photo arrière ; sans matériel de capture, le navigateur
 * retombe de lui-même sur le sélecteur habituel — donc jamais de chemin mort.
 */
function EntreesFichier({
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

function BoutonEnvoi({
  genere,
  envoyable,
  onEnvoyer,
  onAnnuler,
}: {
  genere: boolean;
  envoyable: boolean;
  onEnvoyer: () => void;
  onAnnuler: () => void;
}): ReactElement {
  if (genere) {
    return (
      <Button variant="secondary" size="sm" onClick={onAnnuler}>
        Arrêter
      </Button>
    );
  }
  return (
    <Button variant="primary" size="sm" onClick={onEnvoyer} disabled={!envoyable}>
      Envoyer
    </Button>
  );
}

function BarreSaisie(props: BarreSaisieProps): ReactElement {
  const { texte, genere, desactive, zone, onTexte, onTouche, onColle } = props;
  return (
    <div className={CLASSE_CADRE}>
      <BoutonPiece libelle="Joindre un fichier" desactive={desactive} onClic={props.onChoisirFichier}>
        <IconeTrombone />
      </BoutonPiece>
      <BoutonPiece
        libelle="Prendre une photo"
        desactive={desactive}
        onClic={props.onPrendrePhoto}
        className="lg:hidden"
      >
        <IconeAppareilPhoto />
      </BoutonPiece>
      {/* Pousse l'envoi à droite quand la rangée est repliée sur deux lignes ; sans effet une
          fois `lg:flex-nowrap` actif, où la zone de saisie occupe déjà tout l'espace libre. */}
      <span className="flex-1 lg:hidden" aria-hidden="true" />
      <textarea
        ref={zone}
        rows={1}
        value={texte}
        disabled={desactive}
        onChange={onTexte}
        onKeyDown={onTouche}
        onPaste={onColle}
        placeholder="Écrire un message…"
        className={CLASSE_ZONE_SAISIE}
      />
      <BoutonEnvoi
        genere={genere}
        envoyable={!desactive && texte.trim() !== ''}
        onEnvoyer={props.onEnvoyer}
        onAnnuler={props.onAnnuler}
      />
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
  const entreePhoto = useRef<HTMLInputElement>(null);
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
      className="eh-marge-sure-bas shrink-0 border-t border-border px-3 py-3 lg:px-6 lg:py-4"
      onDragOver={(evenement) => evenement.preventDefault()}
      onDrop={surDepot}
    >
      <div className="mx-auto max-w-3xl">
        <EntreesFichier fichier={entreeFichier} photo={entreePhoto} onChoisir={surSelectionFichier} />
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
          onPrendrePhoto={() => entreePhoto.current?.click()}
        />
        {empechement !== '' && <p className="mt-1.5 text-2xs text-text-3">{empechement}</p>}
      </div>
    </div>
  );
}
