/*
 * Tous les chemins HTTP consommés par le domaine `models`, réunis ici.
 *
 * ATTENTION — au moment où ce fichier est écrit, `backend/models/` n'expose pas encore de routeur
 * FastAPI (le domaine existe, sa couche HTTP est en cours). Les chemins ci-dessous suivent
 * strictement les conventions des routeurs déjà livrés (`system`, `engines`, `chat`) : préfixe de
 * domaine, `/api` ajouté à l'assemblage, noms français alignés sur les fonctions du domaine.
 *
 * C'est le seul fichier à corriger si le routeur définitif diverge. Aucun chemin n'est écrit
 * ailleurs dans le domaine.
 */

export const ROUTES = {
  /** `models.rechercher` — page de dépôts du Hub. */
  recherche: (parametres: {
    requete: string;
    formats: readonly string[];
    capacites: readonly string[];
    tri: string;
    ordre: string;
    page: number;
    taillePage: number;
  }): string => {
    const query = new URLSearchParams({
      requete: parametres.requete,
      tri: parametres.tri,
      ordre: parametres.ordre,
      page: String(parametres.page),
      taille_page: String(parametres.taillePage),
    });
    // Un paramètre répété plutôt qu'une liste séparée par des virgules : c'est ce que FastAPI
    // attend pour un `Query(list[...])`, et ça évite d'encoder une convention de séparateur.
    for (const format of parametres.formats) {
      query.append('formats', format);
    }
    // Même forme répétée pour les capacités, et même sémantique côté backend : elles se combinent
    // en ET. Une sélection vide n'écrit aucun paramètre — l'appel est alors identique à l'ancien.
    for (const capacite of parametres.capacites) {
      query.append('capacites', capacite);
    }
    return `/models/recherche?${query.toString()}`;
  },

  /** `models.lister_capacites` — vocabulaire filtrable, libellés et définitions compris. */
  capacites: '/models/capacites',

  /** `models.details` — fiche complète d'un dépôt, tailles de fichiers comprises. */
  depot: (depot: string): string => `/models/depots/${encodeURIComponent(depot)}`,

  /** `models.lister_modeles` — registre local. */
  registre: '/models/registre',

  /** `models.synchroniser_registre` — réaligne le registre sur le disque. */
  synchronisation: '/models/registre/synchronisation',

  /** `models.oublier_modele` — retire une entrée sans toucher aux fichiers. */
  entreeRegistre: (identifiant: string): string => `/models/registre/${encodeURIComponent(identifiant)}`,

  /** `gestionnaire.lister` / `gestionnaire.demarrer`. */
  telechargements: '/models/telechargements',

  /** `gestionnaire.annuler` — `supprimer_fichiers` décide du sort des octets déjà écrits. */
  telechargement: (identifiant: string, supprimerFichiers: boolean): string =>
    `/models/telechargements/${encodeURIComponent(identifiant)}?supprimer_fichiers=${String(supprimerFichiers)}`,

  /** `gestionnaire.relancer` — reprend là où le transfert s'était arrêté. */
  relance: (identifiant: string): string => `/models/telechargements/${encodeURIComponent(identifiant)}/relance`,
} as const;
