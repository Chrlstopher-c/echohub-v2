/*
 * Forme unique des erreurs côté interface.
 *
 * Le backend sérialise toutes ses erreurs métier avec `EchoHubError.to_dict()` :
 * `{ code, message, remediation, details }`. Ce module garantit que TOUT échec — métier, réseau,
 * réponse illisible — arrive aux écrans sous cette même forme. La v1 laissait remonter des traces
 * Python brutes : impossible d'en tirer quoi faire.
 */

/** Payload d'erreur tel que le backend le produit. `remediation` est ce que l'utilisateur peut faire. */
export interface DetailErreur {
  readonly code: string;
  readonly message: string;
  readonly remediation: string;
  readonly details: Readonly<Record<string, unknown>>;
}

/** Codes produits par le client lui-même, hors du vocabulaire d'erreurs du backend. */
export const CODE_RESEAU = 'reseau_indisponible';
export const CODE_ILLISIBLE = 'reponse_illisible';
export const CODE_DELAI = 'delai_depasse';
export const CODE_FLUX_TROP_LONG = 'flux_trop_long';

export class ErreurApi extends Error {
  /** Statut HTTP, `0` quand la requête n'a jamais atteint le backend. */
  readonly statut: number;
  readonly code: string;
  readonly remediation: string;
  readonly details: Readonly<Record<string, unknown>>;

  constructor(statut: number, detail: DetailErreur) {
    super(detail.message);
    this.name = 'ErreurApi';
    this.statut = statut;
    this.code = detail.code;
    this.remediation = detail.remediation;
    this.details = detail.details;
  }

  /** Vrai si l'utilisateur peut agir : le plan sera dégradé, ou une ressource libérée. */
  get estRecuperable(): boolean {
    return this.statut === 507 || this.statut === 409 || this.statut === 503;
  }
}

function estObjet(valeur: unknown): valeur is Record<string, unknown> {
  return typeof valeur === 'object' && valeur !== null && !Array.isArray(valeur);
}

function texte(valeur: unknown, defaut: string): string {
  return typeof valeur === 'string' && valeur.length > 0 ? valeur : defaut;
}

/** Chemin du champ fautif (`body.demande.preferences.contexte`), remis à plat pour l'affichage. */
function emplacement(valeur: unknown): string {
  if (!Array.isArray(valeur)) return '';
  return valeur.map((partie: unknown) => String(partie)).join('.');
}

/** Erreurs de validation FastAPI : `detail` est une liste `{loc, msg, type}`. */
function depuisValidation(entrees: readonly unknown[]): DetailErreur {
  const lignes = entrees.map((entree: unknown) => {
    if (!estObjet(entree)) return String(entree);
    const chemin = emplacement(entree['loc']);
    const message = texte(entree['msg'], 'valeur refusée');
    return chemin.length > 0 ? `${chemin} : ${message}` : message;
  });
  return {
    code: 'requete_invalide',
    message: lignes.join(' · '),
    remediation: "La requête ne respecte pas le contrat du backend : c'est un défaut de l'interface.",
    details: { validation: entrees },
  };
}

function depuisObjet(detail: Record<string, unknown>, statut: number): DetailErreur {
  const details = estObjet(detail['details']) ? detail['details'] : {};
  return {
    code: texte(detail['code'], `http_${statut}`),
    message: texte(detail['message'], `Le backend a répondu ${statut}.`),
    remediation: texte(detail['remediation'], ''),
    details,
  };
}

/**
 * Normalise un corps d'erreur, quelle que soit sa forme : erreur métier, liste de validation,
 * chaîne nue, ou corps absent. Aucune branche ne peut échouer — c'est le dernier recours avant
 * l'affichage.
 */
export function normaliserErreur(corps: unknown, statut: number): DetailErreur {
  const detail = estObjet(corps) ? corps['detail'] : corps;
  if (Array.isArray(detail)) return depuisValidation(detail);
  if (estObjet(detail)) return depuisObjet(detail, statut);
  if (typeof detail === 'string' && detail.length > 0) {
    return { code: `http_${statut}`, message: detail, remediation: '', details: {} };
  }
  return {
    code: `http_${statut}`,
    message: `Le backend a répondu ${statut} sans détail exploitable.`,
    remediation: 'Consulter les journaux du backend.',
    details: {},
  };
}

/** Échec avant toute réponse HTTP : backend éteint, proxy absent, requête annulée. */
export function erreurReseau(cause: unknown): ErreurApi {
  if (cause instanceof DOMException && cause.name === 'AbortError') {
    return new ErreurApi(0, {
      code: CODE_DELAI,
      message: "La requête a été interrompue avant d'aboutir.",
      remediation: "Réessayer ; si l'opération est longue, augmenter son délai d'attente.",
      details: {},
    });
  }
  return new ErreurApi(0, {
    code: CODE_RESEAU,
    message: 'Le backend est injoignable.',
    remediation: "Vérifier que le backend tourne et que le proxy `/api` pointe sur le bon port.",
    details: { cause: cause instanceof Error ? cause.message : String(cause) },
  });
}
