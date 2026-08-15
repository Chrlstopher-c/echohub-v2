import { useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { Button, cn, MenuContextuel, type EntreeMenu } from '../../shared/design';
import type { ResumeConversation } from '../api/contrats';

/*
 * Colonne des conversations. La sélection se marque par une surface, pas par une bordure ni une
 * couleur d'accent : l'accent est réservé aux actions et à l'activité en cours.
 *
 * Le clic droit ouvre les actions de la conversation. Le bouton de suppression au survol reste :
 * une action uniquement accessible par clic droit serait invisible pour qui ne pense pas à le
 * tenter — le menu enrichit, il ne remplace pas.
 */

interface EntreeProps {
  conversation: ResumeConversation;
  active: boolean;
  onOuvrir: () => void;
  onSupprimer: () => void;
  onRenommer: (titre: string) => void;
}

/* Renommage en place : le titre devient son propre champ, sans modale ni changement d'écran. */
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
        'w-full rounded-sm bg-surface-3 px-2 py-1.5 text-xs text-text',
        'focus:outline-none focus:shadow-[inset_0_0_0_2px_var(--ring)]',
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
    return (
      <li className="relative">
        <ChampTitre
          valeur={conversation.titre}
          onValider={(titre) => {
            onRenommer(titre);
            setRenomme(false);
          }}
          onAnnuler={() => setRenomme(false)}
        />
      </li>
    );
  }

  return (
    <MenuContextuel entrees={entrees} className="group relative block">
      <li className="relative list-none">
        <button
          type="button"
          onClick={onOuvrir}
          className={cn(
            'w-full rounded-sm px-2 py-1.5 text-left transition-colors duration-fast',
            active ? 'bg-surface-2 text-text' : 'text-text-2 hover:bg-surface-2 hover:text-text',
          )}
        >
          <span className="block truncate pr-6 text-xs">{conversation.titre}</span>
          <span className="block font-mono text-2xs tabular-nums text-text-3">
            {conversation.nb_messages} messages
          </span>
        </button>
      <span className="absolute right-1 top-1 hidden group-hover:block">
        <Button variant="ghost" size="sm" aria-label="Supprimer la conversation" onClick={onSupprimer}>
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" aria-hidden="true">
            <path
              d="M3.5 4.5h9M6.5 4.5V3h3v1.5M5 4.5l.5 8h5l.5-8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          </Button>
        </span>
      </li>
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
    <nav className="flex h-full w-60 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center justify-between gap-2 px-3 py-3">
        <h2 className="text-xs font-medium uppercase tracking-wide text-text-3">Conversations</h2>
        <Button variant="secondary" size="sm" onClick={onCreer}>
          Nouvelle
        </Button>
      </div>
      {erreur !== null && <p className="px-3 pb-2 text-2xs text-critical">{erreur}</p>}
      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
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
