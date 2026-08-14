import { motion } from 'framer-motion';
import type { ReactElement } from 'react';
import { Badge, cn, fadeUp } from '../../shared/design';
import type { MessageChat } from '../api/contrats';
import { RenduMarkdown } from '../markdown/RenduMarkdown';
import { formaterDebit } from '../plan/format';

/*
 * Un message. Le tour utilisateur reste du texte brut dans une surface distincte ; la réponse du
 * modèle est rendue en Markdown sur toute la largeur, comme un document.
 *
 * Les statistiques affichées sous une réponse viennent du backend et n'apparaissent que si elles
 * existent : un moteur qui ne rapporte pas son débit ne se voit pas attribuer un chiffre inventé.
 */

function Statistiques({ message }: { message: MessageChat }): ReactElement | null {
  const debit = message.tokens_par_seconde;
  const tokens = message.tokens_generes;
  if (debit === null && tokens === null && !message.interrompu) {
    return null;
  }
  return (
    <div className="mt-1.5 flex items-center gap-2 font-mono text-2xs tabular-nums text-text-3">
      {tokens !== null && <span>{tokens} tokens</span>}
      {debit !== null && <span>{formaterDebit(debit)}</span>}
      {message.interrompu && <Badge tone="caution">interrompu</Badge>}
    </div>
  );
}

export interface MessageProps {
  message: MessageChat;
}

export function Message({ message }: MessageProps): ReactElement {
  const utilisateur = message.role === 'user';
  return (
    <motion.article
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      className={cn('flex', utilisateur ? 'justify-end' : 'justify-start')}
    >
      <div className={cn(utilisateur ? 'max-w-[80%] rounded-md bg-surface-2 px-3 py-2' : 'w-full')}>
        {utilisateur ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-text">{message.contenu}</p>
        ) : (
          <RenduMarkdown source={message.contenu} />
        )}
        {!utilisateur && <Statistiques message={message} />}
      </div>
    </motion.article>
  );
}

export interface MessageEnCoursProps {
  texte: string;
}

/* Réponse en cours de réception : même rendu que la version finale, plus un curseur d'activité. */
export function MessageEnCours({ texte }: MessageEnCoursProps): ReactElement {
  return (
    <article className="w-full">
      {texte === '' ? (
        <p className="text-sm text-text-2">
          <span className="mr-1.5 inline-block h-2 w-2 animate-eh-pulse rounded-full bg-accent align-middle" />
          le modèle répond…
        </p>
      ) : (
        <RenduMarkdown source={texte} />
      )}
    </article>
  );
}
