import type { ReactElement } from 'react';
import { Button, cn } from '../../shared/design';
import type { ResumeConversation } from '../api/contrats';

/*
 * Colonne des conversations. La sélection se marque par une surface, pas par une bordure ni une
 * couleur d'accent : l'accent est réservé aux actions et à l'activité en cours.
 */

interface EntreeProps {
  conversation: ResumeConversation;
  active: boolean;
  onOuvrir: () => void;
  onSupprimer: () => void;
}

function Entree({ conversation, active, onOuvrir, onSupprimer }: EntreeProps): ReactElement {
  return (
    <li className="group relative">
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
  );
}

export interface ListeConversationsProps {
  conversations: ResumeConversation[];
  conversationActive: string | null;
  erreur: string | null;
  onOuvrir: (id: string) => void;
  onCreer: () => void;
  onSupprimer: (id: string) => void;
}

export function ListeConversations({
  conversations,
  conversationActive,
  erreur,
  onOuvrir,
  onCreer,
  onSupprimer,
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
          />
        ))}
      </ul>
    </nav>
  );
}
