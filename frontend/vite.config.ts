import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import checker from 'vite-plugin-checker';

/*
 * Ports lus dans l'environnement, jamais codés en dur : ce sont les mêmes variables que
 * `.env.example` à la racine, pour qu'un seul fichier décide des ports du projet.
 */
// Distincts de la v1 (37822/37821) : les deux versions peuvent tourner en même temps sur le
// même hôte sans se disputer un port.
const PORT_FRONT_DEV = Number(process.env['ECHOHUB_PORT_FRONT_DEV'] ?? 37922);
const PORT_API = Number(process.env['ECHOHUB_PORT_API'] ?? 37921);

/*
 * Le proxy retire `/api` avant de transmettre, exactement comme nginx en production
 * (`rewrite ^/api/(.*)$ /$1` dans docker/nginx.conf). Les routeurs du backend portent `/system`,
 * `/models`, `/engines`, `/inference`, `/chat` — sans préfixe : le laisser passer tel quel
 * donnerait un 404 en dev sur des routes qui fonctionnent en production, la pire des divergences.
 * Une seule règle, énoncée aux deux endroits qui la traversent, et les deux disent la même chose.
 */
export default defineConfig(({ command }) => ({
  plugins: [
    react(),
    // `vite dev` n'exécute pas `tsc` : sans ce vérificateur, une erreur de typage ne se voit qu'au
    // build de production. C'est exactement ainsi que trois erreurs ont survécu à toute la v1.
    //
    // UNIQUEMENT en dev. Au build, le worker que le vérificateur laisse derrière lui empêche le
    // processus de rendre la main : vite affiche « ✓ built », et l'étape ne se termine jamais —
    // 30 minutes perdues sur un build déjà fini. Le script `build` lance de toute façon `tsc`
    // avant `vite build`, la vérification n'est donc pas perdue, seulement faite une seule fois.
    ...(command === 'serve' ? [checker({ typescript: true })] : []),
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
        rewrite: (chemin: string): string => chemin.replace(/^\/api/, ''),
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
}));
