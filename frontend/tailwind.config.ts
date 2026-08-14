import type { Config } from 'tailwindcss';
import { designPreset } from './src/shared/design/tailwind-preset';

/*
 * Le thème vient entièrement du préset du design system : aucune couleur, taille ou rayon n'est
 * défini ici. Ajouter une valeur à cet endroit la rendrait invisible depuis `tokens.css`, donc
 * impossible à faire évoluer avec le reste de la palette.
 */
export default {
  presets: [designPreset],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // Le thème clair est piloté par l'attribut `data-theme` posé sur <html>, pas par une classe :
  // c'est la même bascule que celle qu'attend `tokens.css`.
  darkMode: ['selector', '[data-theme="dark"]'],
} satisfies Config;
