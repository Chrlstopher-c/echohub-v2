import { useEffect, useRef } from 'react';
import type { ReactElement } from 'react';
import type { MessageChat } from '../api/contrats';
import { Message, MessageEnCours } from './Message';

/*
 * Fil de la conversation. Le défilement suit le texte tant que l'utilisateur est au bas du fil ;
 * dès qu'il remonte pour relire, on cesse de le suivre — un fil qui reprend la main pendant qu'on
 * lit est le défaut le plus pénible d'une interface de chat.
 */

/* Marge sous laquelle on considère l'utilisateur « au bas du fil ». */
const SEUIL_BAS_PX = 64;

function estEnBas(element: HTMLElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < SEUIL_BAS_PX;
}

export interface FilMessagesProps {
  messages: MessageChat[];
  brouillon: string | null;
  vide: ReactElement;
}

export function FilMessages({ messages, brouillon, vide }: FilMessagesProps): ReactElement {
  const conteneur = useRef<HTMLDivElement | null>(null);
  const suit = useRef<boolean>(true);

  useEffect((): void => {
    const element = conteneur.current;
    if (element === null || !suit.current) {
      return;
    }
    element.scrollTop = element.scrollHeight;
  }, [messages, brouillon]);

  const surDefilement = (): void => {
    const element = conteneur.current;
    if (element !== null) {
      suit.current = estEnBas(element);
    }
  };

  const aucunContenu = messages.length === 0 && brouillon === null;
  return (
    <div ref={conteneur} onScroll={surDefilement} className="flex-1 overflow-y-auto px-6 py-5">
      {aucunContenu ? (
        vide
      ) : (
        <div className="mx-auto flex max-w-3xl flex-col gap-5">
          {messages.map((message) => (
            <Message key={message.id} message={message} />
          ))}
          {brouillon !== null && <MessageEnCours texte={brouillon} />}
        </div>
      )}
    </div>
  );
}
