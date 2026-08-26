/*
 * Point d'entrée de `/demo.html` — servie par Vite en dev, jamais référencée par l'application :
 * `index.html` ne la connaît pas, et le build de production ne la liste pas dans ses entrées.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// Même ordre d'import CSS que `main.tsx`, pour les mêmes raisons (fond sombre, préflight).
import '../../../shared/design/tokens.css';
import '../../../shared/design/fonts.css';
import '../../../index.css';
import '../../../shared/design/primitives.css';

import { EcranDemo, type SceneDemo } from './EcranDemo';

const SCENES: readonly SceneDemo[] = ['conversation', 'outils', 'artefact', 'liste', 'selection'];

function sceneDemandee(): SceneDemo {
  const brute = new URLSearchParams(window.location.search).get('scene');
  return (SCENES as readonly string[]).includes(brute ?? '') ? (brute as SceneDemo) : 'conversation';
}

const racine = document.getElementById('racine');
if (racine === null) {
  throw new Error('Élément #racine introuvable dans demo.html.');
}

createRoot(racine).render(
  <StrictMode>
    <EcranDemo scene={sceneDemandee()} />
  </StrictMode>,
);
