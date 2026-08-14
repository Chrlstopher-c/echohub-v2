import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// Ordre significatif : tokens et polices d'abord (ils ne dépendent de rien), puis le preflight
// Tailwind, puis les primitives qui doivent le surcharger. Inverser fait perdre le fond sombre.
import './shared/design/tokens.css';
import './shared/design/fonts.css';
import './index.css';
import './shared/design/primitives.css';

import { App } from './App';

const racine = document.getElementById('racine');

// Échouer bruyamment plutôt que rendre dans le vide : un `index.html` modifié sans ce fichier
// donnerait une page blanche sans la moindre trace en console.
if (racine === null) {
  throw new Error("Élément #racine introuvable dans index.html : impossible de monter l'interface.");
}

createRoot(racine).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
