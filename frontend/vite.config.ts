import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import checker from 'vite-plugin-checker';

/*
 * Ports lus dans l'environnement, jamais codés en dur : ce sont les mêmes variables que
 * `.env.example` à la racine, pour qu'un seul fichier décide des ports du projet.
 */
const PORT_FRONT_DEV = Number(process.env['ECHOHUB_PORT_FRONT_DEV'] ?? 37822);
const PORT_API = Number(process.env['ECHOHUB_PORT_API'] ?? 37821);

/*
 * Le proxy ne réécrit PAS l'URL. Les routeurs du backend portent déjà `/api` une fois assemblés
 * (`/api/system`, `/api/chat`, `/api/engines`, `/api/inference`) : ce que voit le backend en dev
 * est donc exactement ce que nginx lui transmettra en production. La v1 réécrivait `/api` -> `/`
 * côté nginx ET côté Vite, ce qui obligeait à maintenir la même règle à deux endroits.
 */
export default defineConfig({
  plugins: [
    react(),
    // `vite dev` n'exécute pas `tsc` : sans ce vérificateur, une erreur de typage ne se voit qu'au
    // build de production. C'est exactement ainsi que trois erreurs ont survécu à toute la v1.
    checker({ typescript: true }),
  ],
  resolve: {
    // Doit rester le miroir exact de `paths` dans tsconfig.json : un alias connu de `tsc` seul
    // passerait la vérification de types puis casserait au chargement du module.
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: PORT_FRONT_DEV,
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${PORT_API}`,
        changeOrigin: true,
        // Le SSE (génération, installation de moteur) doit arriver morceau par morceau : un proxy
        // qui tamponne rend le streaming invisible et fait croire à un blocage.
        ws: false,
        timeout: 0,
        proxyTimeout: 0,
      },
    },
  },
  build: {
    outDir: 'dist',
    // Les sources de production servent au diagnostic d'un plan de chargement en conditions
    // réelles : sans elles, une erreur d'écran remonte illisible.
    sourcemap: true,
  },
});
