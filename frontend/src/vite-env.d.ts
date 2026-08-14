/// <reference types="vite/client" />

/*
 * Variables d'environnement du frontend, déclarées explicitement.
 * Sans cette déclaration, `import.meta.env.VITE_*` serait typé `any` — le contraire de ce que
 * ce projet exige. Toute nouvelle variable doit être ajoutée ici avant d'être lue.
 */
interface ImportMetaEnv {
  /**
   * Racine de l'API. Vide par défaut : le client utilise `/api` en relatif, servi par le proxy
   * Vite en développement et par nginx en production. À ne renseigner que si le frontend tourne
   * sur une origine différente du backend.
   */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
