/*
 * Corps de rendu d'une version d'artefact — pur : le contenu arrive en props, aucun réseau ici.
 * C'est ce qui permet au panneau, à la modale agrandie et à la page de démonstration de partager
 * exactement le même rendu, et aux captures d'être produites sans backend.
 *
 * Tout contenu vient d'un modèle : entrée NON FIABLE. Les types qui se rendent (html, svg) passent
 * par une iframe `sandbox` sans `allow-same-origin` — origine opaque, aucun accès aux cookies ni
 * au stockage de l'application. Le SVG n'obtient même pas `allow-scripts` : une image n'exécute
 * rien. Un type inconnu retombe sur du texte brut, jamais sur une page blanche.
 */

import type { ReactElement } from 'react';
import { RenduMarkdown } from '../markdown';
import { BlocCode } from '../markdown/BlocCode';
import type { TypeArtefact, VersionArtefact } from './detection';

export type VueAtelier = 'code' | 'apercu';

/** Les types dont l'aperçu a un sens ; les autres n'offrent que la vue code. */
export function apercuPossible(type: TypeArtefact | 'inconnu'): boolean {
  return type === 'html' || type === 'svg' || type === 'markdown';
}

const LANGAGE_PAR_TYPE: Readonly<Record<string, string>> = {
  html: 'html',
  markdown: 'md',
  svg: 'xml',
  mermaid: 'mermaid',
  inconnu: 'txt',
};

function langagePour(version: VersionArtefact): string {
  if (version.type === 'code') {
    return version.langage ?? 'txt';
  }
  return LANGAGE_PAR_TYPE[version.type] ?? 'txt';
}

/* Enveloppe minimale pour servir un SVG seul dans l'iframe : fond transparent, centré, sans marge. */
function pageSvg(contenu: string): string {
  const style = 'margin:0;display:grid;min-height:100vh;place-items:center';
  return `<!doctype html><html><body style="${style}">${contenu}</body></html>`;
}

function ApercuRendu({ version, contenu }: { version: VersionArtefact; contenu: string }): ReactElement {
  if (version.type === 'markdown') {
    return (
      <div className="h-full overflow-y-auto px-3 py-2">
        <RenduMarkdown source={contenu} />
      </div>
    );
  }
  return (
    <iframe
      title={`Aperçu — ${version.titre}`}
      // `allow-scripts` seulement pour une page : elle est faite pour être manipulée. Jamais
      // `allow-same-origin` — voir l'entête du fichier.
      sandbox={version.type === 'html' ? 'allow-scripts' : ''}
      srcDoc={version.type === 'svg' ? pageSvg(contenu) : contenu}
      data-testid="apercu-artefact"
      className="h-full w-full rounded-sm bg-white"
    />
  );
}

function CodeRendu({ version, contenu }: { version: VersionArtefact; contenu: string }): ReactElement {
  return (
    <div className="h-full overflow-y-auto px-3 py-2">
      {version.type === 'mermaid' && (
        <p className="mb-2 text-2xs leading-relaxed text-text-3">
          Le rendu du diagramme n’est pas disponible : aucune bibliothèque mermaid n’est embarquée —
          en ajouter une est une décision de dépendance, pas d’affichage. La source reste lisible.
        </p>
      )}
      <BlocCode texte={contenu} langage={langagePour(version)} complet />
    </div>
  );
}

export interface VueArtefactProps {
  readonly version: VersionArtefact;
  readonly contenu: string;
  readonly vue: VueAtelier;
}

export function VueArtefact({ version, contenu, vue }: VueArtefactProps): ReactElement {
  if (vue === 'apercu' && apercuPossible(version.type)) {
    return <ApercuRendu version={version} contenu={contenu} />;
  }
  return <CodeRendu version={version} contenu={contenu} />;
}
