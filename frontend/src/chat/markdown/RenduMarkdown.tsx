import { useMemo } from 'react';
import type { ReactElement } from 'react';
import { cn } from '../../shared/design';
import { BlocCode } from './BlocCode';
import { analyserMarkdown } from './parseur';
import type { Alignement, BlocListe, BlocMarkdown, BlocTableau, NiveauTitre, SegmentInline } from './types';

/*
 * Rendu de l'arbre Markdown en éléments React. Aucune chaîne n'est injectée en HTML : React échappe
 * tout ce qui passe par ses enfants, ce qui rend le rendu d'une sortie de modèle sûr par construction.
 *
 * L'emphase ne se rend PAS en italique (DESIGN.md l'exclut de l'interface) : elle passe par la
 * graisse, comme le reste des accentuations du produit.
 *
 * Les titres se composent en `<p>` et non en `<h1>`…`<h6>` : une réponse s'insère dans un fil de
 * conversation qui a déjà sa hiérarchie de titres, et six niveaux de plus par message la rendraient
 * illisible pour un lecteur d'écran. La hiérarchie visuelle vient de la graisse et de la taille.
 */

const CLASSE_TITRE: Record<NiveauTitre, string> = {
  1: 'text-lg font-semibold text-text',
  2: 'text-md font-semibold text-text',
  3: 'text-sm font-semibold text-text',
  4: 'text-sm font-medium text-text',
  5: 'text-xs font-semibold text-text-2',
  6: 'text-xs font-medium text-text-2',
};

const CLASSE_ALIGNEMENT: Record<Alignement, string> = {
  gauche: 'text-left',
  centre: 'text-center',
  droite: 'text-right',
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

/* Récursif : un item porte sa sous-liste, la profondeur est déjà bornée par l'analyse. */
function Liste({ bloc }: { bloc: BlocListe }): ReactElement {
  const Balise = bloc.ordonnee ? 'ol' : 'ul';
  return (
    <Balise
      className={cn(
        'my-1.5 space-y-1 pl-5 marker:text-text-3',
        bloc.ordonnee ? 'list-decimal' : 'list-disc',
      )}
    >
      {bloc.items.map((item, index) => (
        <li key={index}>
          <Inline segments={item.contenu} />
          {item.sousListe !== null && <Liste bloc={item.sousListe} />}
        </li>
      ))}
    </Balise>
  );
}

/* La largeur d'une réponse n'est pas garantie : le tableau défile dans son propre cadre plutôt que
 * de pousser toute la conversation en débordement horizontal. */
function Tableau({ bloc }: { bloc: BlocTableau }): ReactElement {
  const aligner = (colonne: number): string => CLASSE_ALIGNEMENT[bloc.alignements[colonne] ?? 'gauche'];
  return (
    <div className="my-2 overflow-x-auto rounded-sm border border-border">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border bg-surface-2">
            {bloc.entetes.map((cellule, colonne) => (
              <th key={colonne} scope="col" className={cn('px-2.5 py-1.5 font-medium text-text', aligner(colonne))}>
                <Inline segments={cellule} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bloc.lignes.map((rangee, index) => (
            <tr key={index} className="border-t border-border">
              {rangee.map((cellule, colonne) => (
                <td key={colonne} className={cn('px-2.5 py-1.5 align-top text-text-2', aligner(colonne))}>
                  <Inline segments={cellule} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Bloc({ bloc }: { bloc: BlocMarkdown }): ReactElement {
  switch (bloc.type) {
    case 'code':
      return <BlocCode texte={bloc.texte} langage={bloc.langage} complet={bloc.complet} />;
    case 'titre':
      return <p className={`mt-3 first:mt-0 ${CLASSE_TITRE[bloc.niveau]}`}><Inline segments={bloc.contenu} /></p>;
    case 'liste':
      return <Liste bloc={bloc} />;
    case 'tableau':
      return <Tableau bloc={bloc} />;
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
