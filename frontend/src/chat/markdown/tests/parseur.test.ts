/*
 * Tests purs de l'analyse Markdown — aucune dépendance, aucun rendu, aucun navigateur.
 *
 * Lancement : `bun run frontend/src/chat/markdown/tests/parseur.test.ts`
 * Le fichier lève à la fin s'il reste un échec : le code de sortie est non nul, exploitable en CI.
 *
 * Le harnais est volontairement recopié dans les deux dossiers de tests (ici et `raisonnement/`)
 * plutôt que mutualisé : mutualiser créerait un import entre deux modules qui n'ont aucune raison
 * de se connaître, pour douze lignes qui n'évolueront pas.
 */

import { analyserMarkdown } from '../parseur';
import type { BlocMarkdown, SegmentInline } from '../types';

let echecs = 0;

function verifier(nom: string, obtenu: unknown, attendu: unknown): void {
  const gauche = JSON.stringify(obtenu);
  const droite = JSON.stringify(attendu);
  if (gauche === droite) {
    console.log(`ok    ${nom}`);
    return;
  }
  echecs += 1;
  console.error(`ÉCHEC ${nom}\n  obtenu  : ${gauche}\n  attendu : ${droite}`);
}

/** Accès garde-fou : un bloc absent doit faire échouer le test, pas rendre `undefined`. */
function bloc(source: string, index: number): BlocMarkdown {
  const blocs = analyserMarkdown(source);
  const trouve = blocs[index];
  if (trouve === undefined) {
    throw new Error(`bloc ${index} absent — ${blocs.length} bloc(s) analysé(s) pour : ${source}`);
  }
  return trouve;
}

/** Texte brut d'une suite de segments : sert à vérifier qu'aucun caractère n'est perdu. */
function texteBrut(segments: SegmentInline[]): string {
  return segments.map((segment) => segment.texte).join('');
}

function testerTitresEtCode(): void {
  const titre = bloc('#### Étape 2', 0);
  verifier('titre `####` lu au niveau 4', titre.type === 'titre' ? titre.niveau : null, 4);
  const titre6 = bloc('###### Détail', 0);
  verifier('titre `######` lu au niveau 6', titre6.type === 'titre' ? titre6.niveau : null, 6);
  const faux = bloc('#pas un titre', 0);
  verifier('dièse sans espace reste un paragraphe', faux.type, 'paragraphe');

  const ouvert = bloc('```py\nprint(1)', 0);
  verifier(
    'bloc de code non refermé garde son texte et se déclare incomplet',
    ouvert.type === 'code' ? [ouvert.complet, ouvert.texte, ouvert.langage] : null,
    [false, 'print(1)', 'py'],
  );
  const ferme = bloc('```\nx = 1\n```', 0);
  verifier('bloc de code refermé', ferme.type === 'code' ? [ferme.complet, ferme.texte] : null, [true, 'x = 1']);
}

function testerListes(): void {
  const imbriquee = bloc('- a\n  - a1\n  - a2\n- b', 0);
  const items = imbriquee.type === 'liste' ? imbriquee.items : [];
  verifier('liste imbriquée : deux items au niveau haut', items.length, 2);
  const sous = items[0]?.sousListe;
  verifier('sous-liste rattachée au bon item', sous?.items.length ?? null, 2);
  verifier('item sans sous-liste reste à null', items[1]?.sousListe ?? null, null);

  const mixte = bloc('- étapes\n  1. un\n  2. deux', 0);
  const sousMixte = mixte.type === 'liste' ? mixte.items[0]?.sousListe : null;
  verifier('sous-liste numérotée sous une puce', [sousMixte?.ordonnee, sousMixte?.items.length], [true, 2]);

  const continuee = bloc('- premier\n  suite du premier\n- second', 0);
  const itemsContinues = continuee.type === 'liste' ? continuee.items : [];
  verifier('ligne indentée rattachée à son item', itemsContinues.length, 2);
  verifier(
    'texte de la continuation conservé',
    texteBrut(itemsContinues[0]?.contenu ?? []),
    'premier suite du premier',
  );

  const separateur = bloc('---', 0);
  verifier('`---` reste un séparateur, pas un item de liste', separateur.type, 'separateur');
}

function testerTableaux(): void {
  const source = '| Modèle | VRAM |\n|:---|---:|\n| A | 10 |\n| B | 12 |';
  const tableau = bloc(source, 0);
  verifier('tableau reconnu', tableau.type, 'tableau');
  if (tableau.type !== 'tableau') {
    return;
  }
  verifier('alignements lus dans les délimiteurs', tableau.alignements, ['gauche', 'droite']);
  verifier('en-têtes découpées', tableau.entetes.map(texteBrut), ['Modèle', 'VRAM']);
  verifier('rangées lues', tableau.lignes.length, 2);

  const enCours = bloc('| a | b |\n|---|---|', 0);
  verifier(
    'tableau sans rangée pendant le streaming',
    enCours.type === 'tableau' ? enCours.lignes.length : null,
    0,
  );

  const courte = bloc('| a | b |\n|---|---|\n| 1', 0);
  const rangee = courte.type === 'tableau' ? courte.lignes[0] : undefined;
  verifier('rangée courte complétée à la largeur des colonnes', rangee?.length ?? null, 2);

  const prose = bloc('un texte | avec une barre\nsuite', 0);
  verifier('une barre verticale seule ne fait pas un tableau', prose.type, 'paragraphe');
}

function testerInline(): void {
  const paragraphe = bloc('**gras** et `code` et [lien](https://exemple.fr)', 0);
  const segments = paragraphe.type === 'paragraphe' ? paragraphe.contenu : [];
  verifier(
    'types de segments inline',
    segments.map((segment) => segment.type),
    ['fort', 'texte', 'code', 'texte', 'lien'],
  );
  const lien = segments[4];
  verifier('href du lien', lien?.type === 'lien' ? lien.href : null, 'https://exemple.fr');

  const inacheve = bloc('**gras jamais fermé', 0);
  verifier(
    'marqueur inline non refermé reste du texte visible',
    inacheve.type === 'paragraphe' ? texteBrut(inacheve.contenu) : null,
    '**gras jamais fermé',
  );

  const identifiant = bloc('la variable nom_de_variable_ici est intacte', 0);
  verifier(
    'les tirets bas ne coupent pas un identifiant',
    identifiant.type === 'paragraphe' ? texteBrut(identifiant.contenu) : null,
    'la variable nom_de_variable_ici est intacte',
  );

  const citation = bloc('> une citation', 0);
  verifier('citation reconnue', citation.type, 'citation');
}

testerTitresEtCode();
testerListes();
testerTableaux();
testerInline();

if (echecs > 0) {
  throw new Error(`${echecs} test(s) en échec`);
}
console.log('analyse Markdown : tous les tests passent');
