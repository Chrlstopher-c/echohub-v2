import { useMemo } from 'react';
import type { ReactElement } from 'react';
import { BlocCode } from './BlocCode';
import { analyserMarkdown } from './parseur';
import type { BlocMarkdown, SegmentInline } from './parseur';

/*
 * Rendu de l'arbre Markdown en éléments React. Aucune chaîne n'est injectée en HTML : React échappe
 * tout ce qui passe par ses enfants, ce qui rend le rendu d'une sortie de modèle sûr par construction.
 *
 * L'emphase ne se rend PAS en italique (DESIGN.md l'exclut de l'interface) : elle passe par la
 * graisse, comme le reste des accentuations du produit.
 */

const CLASSE_TITRE: Record<1 | 2 | 3, string> = {
  1: 'text-lg font-semibold text-text',
  2: 'text-md font-semibold text-text',
  3: 'text-sm font-semibold text-text',
};

function Inline({ segments }: { segments: SegmentInline[] }): ReactElement {
  return (
    <>
      {segments.map((segment, index) => {
        if (segment.type === 'code') {
          return (
            <code key={index} className="rounded-xs bg-surface-2 px-1 font-mono text-xs text-text">
              {segment.texte}
            </code>
          );
        }
        if (segment.type === 'fort' || segment.type === 'emphase') {
          return (
            <strong key={index} className="font-semibold text-text">
              {segment.texte}
            </strong>
          );
        }
        if (segment.type === 'lien') {
          return <Lien key={index} texte={segment.texte} href={segment.href} />;
        }
        return <span key={index}>{segment.texte}</span>;
      })}
    </>
  );
}

function Lien({ texte, href }: { texte: string; href: string }): ReactElement {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="text-accent underline decoration-border-strong underline-offset-2 hover:decoration-accent"
    >
      {texte}
    </a>
  );
}

function Bloc({ bloc }: { bloc: BlocMarkdown }): ReactElement {
  switch (bloc.type) {
    case 'code':
      return <BlocCode texte={bloc.texte} langage={bloc.langage} complet={bloc.complet} />;
    case 'titre':
      return <p className={`mt-3 first:mt-0 ${CLASSE_TITRE[bloc.niveau]}`}><Inline segments={bloc.contenu} /></p>;
    case 'liste':
      return <Liste ordonnee={bloc.ordonnee} items={bloc.items} />;
    case 'citation':
      return (
        <blockquote className="my-2 border-l-2 border-border-strong pl-3 text-text-2">
          <Inline segments={bloc.contenu} />
        </blockquote>
      );
    case 'separateur':
      return <hr className="my-3 border-0 border-t border-border" />;
    default:
      return <p className="whitespace-pre-wrap"><Inline segments={bloc.contenu} /></p>;
  }
}

function Liste({ ordonnee, items }: { ordonnee: boolean; items: SegmentInline[][] }): ReactElement {
  const classe = ordonnee ? 'list-decimal' : 'list-disc';
  const Balise = ordonnee ? 'ol' : 'ul';
  return (
    <Balise className={`my-1.5 space-y-1 pl-5 ${classe} marker:text-text-3`}>
      {items.map((item, index) => (
        <li key={index}>
          <Inline segments={item} />
        </li>
      ))}
    </Balise>
  );
}

export interface RenduMarkdownProps {
  source: string;
}

export function RenduMarkdown({ source }: RenduMarkdownProps): ReactElement {
  // Le streaming remplace `source` à chaque fragment : l'analyse est mémoïsée sur le texte reçu.
  const blocs = useMemo(() => analyserMarkdown(source), [source]);
  return (
    <div className="space-y-2 text-sm leading-relaxed text-text">
      {blocs.map((bloc, index) => (
        <Bloc key={index} bloc={bloc} />
      ))}
    </div>
  );
}
