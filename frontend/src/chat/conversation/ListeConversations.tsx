import { useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { BoutonActions, Button, cn, MenuContextuel, type EntreeMenu } from '../../shared/design';
import type { ResumeConversation } from '../api/contrats';

/*
 * Colonne des conversations. La sélection se marque par une surface, pas par une bordure ni une
 * couleur d'accent : l'accent est réservé aux actions et à l'activité en cours.
 *
 * Le clic droit ouvre les actions de la conversation. L'exigence d'origine — « une action seulement
 * au clic droit serait invisible » — est tenue par un déclencheur PERMANENT (`BoutonActions`) et non
 * plus par un bouton révélé au survol : le survol n'existe pas au doigt, l'ancienne corbeille y était
 * donc simplement absente. Une seule voie mène désormais à Supprimer, celle du menu.
 */

interface EntreeProps {
  conversation: ResumeConversation;
  active: boolean;
  onOuvrir: () => void;
  onSupprimer: () => void;
  onRenommer: (titre: string) => void;
}

/*
 * Renommage en place. Le champ prend EXACTEMENT la place du titre : mêmes marges, même taille de
 * texte, et la ligne « n messages » reste dessous. Un champ de formulaire ordinaire romprait la
 * colonne — l'utilisateur doit voir le titre devenir modifiable, pas voir la ligne être remplacée
 * par autre chose.
 *
 * L'état de saisie se marque par la surface active de la ligne et une bordure de la même famille
 * que le reste, jamais par un anneau de focus épais : la ligne fait 3 mm de haut, un anneau de 2 px
 * y devient la forme dominante.
 */
function ChampTitre({ valeur, onValider, onAnnuler }: {
  valeur: string;
  onValider: (titre: string) => void;
  onAnnuler: () => void;
}): ReactElement {
  const [texte, setTexte] = useState(valeur);
  const champ = useRef<HTMLInputElement>(null);
  useEffect(() => champ.current?.select(), []);
  const valider = (): void => {
    const propre = texte.trim();
    if (propre !== '' && propre !== valeur) onValider(propre);
    else onAnnuler();
  };
  return (
    <input
      ref={champ}
      value={texte}
      onChange={(e) => setTexte(e.target.value)}
      onBlur={valider}
      onKeyDown={(e) => {
        if (e.key === 'Enter') valider();
        if (e.key === 'Escape') onAnnuler();
      }}
      className={cn(
        'w-full rounded-[3px] border border-accent bg-bg px-1 py-0 text-xs text-text',
        'focus:outline-none',
      )}
      aria-label="Renommer la conversation"
    />
  );
}

function Entree({ conversation, active, onOuvrir, onSupprimer, onRenommer }: EntreeProps): ReactElement {
  const [renomme, setRenomme] = useState(false);

  const entrees: EntreeMenu[] = [
    { libelle: 'Ouvrir', onChoisir: onOuvrir, desactivee: active },
    { libelle: 'Renommer', onChoisir: () => setRenomme(true) },
    { libelle: 'Copier le titre', onChoisir: () => void navigator.clipboard?.writeText(conversation.titre) },
    { libelle: 'Supprimer', onChoisir: onSupprimer, destructive: true },
  ];

  if (renomme) {
    // Même enveloppe que la ligne normale — surface active, marges et interligne identiques — pour
    // que seule la nature du titre change, pas la géométrie de la colonne.
    return (
      <li className="relative list-none rounded-sm bg-surface-2 px-2 py-1.5">
        <ChampTitre
          valeur={conversation.titre}
          onValider={(titre) => {
            onRenommer(titre);
            setRenomme(false);
          }}
          onAnnuler={() => setRenomme(false)}
        />
        <span className="block font-mono text-2xs tabular-nums text-text-3">
          {conversation.nb_messages} messages
        </span>
      </li>
    );
  }

  return (
    <MenuContextuel entrees={entrees} className="group relative block">
      {({ ouvrirDepuis }) => (
        <li className="relative flex list-none items-center">
          <button
            type="button"
            onClick={onOuvrir}
            className={cn(
              'min-w-0 flex-1 rounded-sm px-2 py-1.5 text-left transition-colors duration-fast',
              active ? 'bg-surface-2 text-text' : 'text-text-2 hover:bg-surface-2 hover:text-text',
            )}
          >
            <span className="block truncate text-xs">{conversation.titre}</span>
            <span className="block font-mono text-2xs tabular-nums text-text-3">
              {conversation.nb_messages} messages
            </span>
          </button>
          {/* Permanent au doigt ; sur grand écran il reste révélé au survol (ou au focus clavier),
              exactement comme la corbeille qu'il remplace — la densité de la colonne est intacte. */}
          <BoutonActions
            libelle="Actions sur la conversation"
            onClick={(evenement) => ouvrirDepuis(evenement.currentTarget)}
            className={cn(
              'lg:pointer-events-none lg:opacity-0',
              'lg:group-hover:pointer-events-auto lg:group-hover:opacity-100',
              'lg:focus-visible:pointer-events-auto lg:focus-visible:opacity-100',
            )}
          />
        </li>
      )}
    </MenuContextuel>
  );
}

export interface ListeConversationsProps {
  conversations: ResumeConversation[];
  conversationActive: string | null;
  erreur: string | null;
  onOuvrir: (id: string) => void;
  onCreer: () => void;
  onSupprimer: (id: string) => void;
  onRenommer: (id: string, titre: string) => void;
}

export function ListeConversations({
  conversations,
  conversationActive,
  erreur,
  onOuvrir,
  onCreer,
  onSupprimer,
  onRenommer,
}: ListeConversationsProps): ReactElement {
  return (
    // Dans le tiroir, la largeur et la bordure viennent du panneau : `w-60` y créerait une colonne
    // de 240 px dans un panneau de 320, avec un vide à droite.
    <nav
      className={cn(
        'flex h-full w-full min-w-0 flex-col bg-surface',
        'lg:w-60 lg:shrink-0 lg:border-r lg:border-border',
      )}
    >
      <div className="flex items-center gap-2 px-3 py-3">
        {/* Le titre est déjà porté par l'entête du tiroir sous le seuil — le répéter volerait une
            ligne sur un écran qui n'en a pas de trop. */}
        <h2 className="hidden text-xs font-medium uppercase tracking-wide text-text-3 lg:block">Conversations</h2>
        <Button variant="secondary" size="sm" className="ml-auto" onClick={onCreer}>
          Nouvelle
        </Button>
      </div>
      {erreur !== null && <p className="px-3 pb-2 text-2xs text-critical">{erreur}</p>}
      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto overflow-x-hidden px-2 pb-3">
        {conversations.map((conversation) => (
          <Entree
            key={conversation.id}
            conversation={conversation}
            active={conversation.id === conversationActive}
            onOuvrir={() => onOuvrir(conversation.id)}
            onSupprimer={() => onSupprimer(conversation.id)}
            onRenommer={(titre) => onRenommer(conversation.id, titre)}
          />
        ))}
      </ul>
    </nav>
  );
}
