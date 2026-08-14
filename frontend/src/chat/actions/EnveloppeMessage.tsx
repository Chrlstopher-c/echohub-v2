/*
 * Enveloppe d'un message : ce qui rend ses actions et ses variantes atteignables.
 *
 * Trois contraintes tiennent la mise en page :
 *
 * 1. Rien ne bouge à l'apparition. La rangée d'actions est HORS FLUX (`absolute` dans un conteneur
 *    de hauteur nulle, ancré au bas du message) : elle se pose dans l'espace inter-messages sans
 *    jamais repousser le texte. Réserver sa hauteur en flux coûterait une bande vide sous chaque
 *    message, sur un écran dont DESIGN.md exige la densité.
 * 2. Survol ET focus clavier. `group-hover` seul rendrait les actions inatteignables sans souris ;
 *    `group-focus-within` les révèle dès qu'un de leurs boutons prend le focus par tabulation.
 * 3. Pointeur grossier. Sur un appareil sans survol, la rangée reste affichée en retrait
 *    (opacité réduite) plutôt que masquée : une action sans second chemin d'accès n'existe pas.
 *
 * La navigation entre variantes, elle, n'est PAS conditionnée au survol — c'est une information sur
 * l'état de la conversation, pas une action.
 */

import type { ReactElement, ReactNode } from 'react';
import type { MessageChat } from '../api/contrats';
import { useActionsMessages, type ActionsMessages } from './fournisseur';
import { EditeurEnPlace } from './EditeurEnPlace';
import { NavigationBranches } from './NavigationBranches';
import { RangeeActions } from './RangeeActions';

const CLASSE_REVELEE =
  'ml-auto pointer-events-none opacity-0 transition-opacity duration-fast ease-out ' +
  'group-hover/msg:pointer-events-auto group-hover/msg:opacity-100 ' +
  'group-focus-within/msg:pointer-events-auto group-focus-within/msg:opacity-100 ' +
  '[@media(hover:none)]:pointer-events-auto [@media(hover:none)]:opacity-60';

interface BarreProps {
  message: MessageChat;
  actions: ActionsMessages;
}

function Barre({ message, actions }: BarreProps): ReactElement {
  const freres = actions.variantes[message.id] ?? [];
  const index = freres.indexOf(message.id);
  const activer = (cible: string | undefined): void => {
    if (cible !== undefined) {
      actions.activerVariante(cible);
    }
  };
  return (
    <div className="pointer-events-none absolute inset-x-0 top-full z-10 flex h-0 items-start gap-2">
      {index >= 0 && freres.length > 1 && (
        <span className="pointer-events-auto pt-1">
          <NavigationBranches
            position={index + 1}
            total={freres.length}
            occupe={actions.occupe}
            onPrecedente={() => activer(freres[index - 1])}
            onSuivante={() => activer(freres[index + 1])}
          />
        </span>
      )}
      <span className={CLASSE_REVELEE}>
        <RangeeActions
          texte={message.contenu}
          editable={message.role === 'user'}
          rejouable={message.role !== 'system'}
          occupe={actions.occupe}
          onEditer={() => actions.demarrerEdition(message)}
          onRejouer={() => actions.rejouer(message)}
        />
      </span>
    </div>
  );
}

interface CorpsProps extends BarreProps {
  children: ReactNode;
}

function CorpsActionnable({ message, actions, children }: CorpsProps): ReactElement {
  if (actions.messageEnEdition === message.id) {
    return (
      <EditeurEnPlace
        contenuInitial={message.contenu}
        occupe={actions.occupe}
        onAnnuler={actions.annulerEdition}
        onConfirmer={(contenu) => actions.confirmerEdition(message, contenu)}
      />
    );
  }
  return (
    <div className="group/msg relative">
      {children}
      <Barre message={message} actions={actions} />
    </div>
  );
}

export interface EnveloppeMessageProps {
  message: MessageChat;
  /** Le message rendu tel qu'il l'est déjà : bulle utilisateur ou Markdown de la réponse. */
  children: ReactNode;
}

/**
 * À poser autour du corps d'un message dans le fil. Hors fournisseur d'actions, elle est neutre et
 * rend ses enfants inchangés : un message affiché dans un autre contexte reste un message.
 */
export function EnveloppeMessage({ message, children }: EnveloppeMessageProps): ReactElement {
  const actions = useActionsMessages();
  if (actions === null) {
    return <>{children}</>;
  }
  return (
    <CorpsActionnable message={message} actions={actions}>
      {children}
    </CorpsActionnable>
  );
}
