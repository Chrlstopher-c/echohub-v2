import type { ReactElement } from 'react';
import { Badge } from '../../shared/design';
import type { MessageChat } from '../api/contrats';
import { formaterTokens } from '../plan/format';
import { bilanReponses, type BilanReponses, type ReponseMesuree } from './mesures';

/*
 * Le plafond confronté à ce qu'il a produit ICI — la seule réponse honnête à « pourquoi mes
 * réponses sont coupées ».
 *
 * Le symptôme rapporté est un modèle qui « réfléchit » longuement et rend une réponse tronquée. La
 * cause n'est pas devinée : elle est lisible dans les messages déjà persistés. Une réponse dont le
 * moteur rapporte exactement autant de jetons que le plafond a été coupée par lui, ce n'est pas une
 * interprétation. Un bloc `<think>` ouvert et jamais refermé prouve que la coupure est tombée
 * pendant le raisonnement, avant qu'une conclusion n'existe.
 *
 * Ce qui n'est PAS fait ici : convertir des caractères en jetons. Les deux grandeurs cohabitent
 * sans jamais se mélanger, et la part du raisonnement en jetons reste l'affaire du panneau de
 * contexte, qui dispose du tokenizer du modèle chargé.
 */

function Mecanisme({ plafond }: { plafond: number | null }): ReactElement {
  if (plafond === null) {
    return (
      <p className="text-2xs leading-snug text-text-2">
        Aucun plafond : la génération s’arrête sur la fenêtre de contexte servie par le moteur, ou
        sur une séquence d’arrêt.
      </p>
    );
  }
  return (
    <p className="text-2xs leading-snug text-text-2">
      Le plafond compte <span className="text-text">tous</span> les jetons produits, blocs
      {' <think> '}
      compris : ce que le modèle dépense à réfléchir n’est plus disponible pour la réponse.
    </p>
  );
}

function LigneMesure({ mesure }: { mesure: ReponseMesuree }): ReactElement {
  const { raisonnement, caracteres, tokens } = mesure;
  return (
    <p className="font-mono text-2xs leading-relaxed tabular-nums text-text-2">
      {`Plus longue réponse mesurée : ${formaterTokens(tokens)} jetons`}
      {raisonnement.caracteres > 0
        && ` — ${formaterTokens(raisonnement.caracteres)} caractères sur `
          + `${formaterTokens(caracteres)} dans des blocs <think>`}
    </p>
  );
}

interface ConstatProps {
  readonly bilan: BilanReponses;
  readonly plafond: number | null;
}

function Constat({ bilan, plafond }: ConstatProps): ReactElement {
  const { plusLongue, auPlafond, mesurees, reponses } = bilan;
  if (plusLongue === null) {
    return (
      <p className="text-2xs text-text-3">
        {reponses === 0
          ? 'Aucune réponse dans cette conversation : rien à confronter au plafond.'
          : `${formaterTokens(reponses)} réponse(s), aucune mesurée par le moteur : rien à confronter.`}
      </p>
    );
  }
  return (
    <div className="space-y-1.5">
      <LigneMesure mesure={plusLongue} />
      <div className="flex flex-wrap items-center gap-1.5">
        {auPlafond > 0 && plafond !== null && (
          <Badge tone="caution">
            {`${formaterTokens(auPlafond)} sur ${formaterTokens(mesurees)} arrêtées au plafond`}
          </Badge>
        )}
        {plusLongue.raisonnement.nonReferme && (
          <Badge tone="caution">raisonnement jamais refermé</Badge>
        )}
      </div>
    </div>
  );
}

export interface PlafondReponsesProps {
  /**
   * Plafond actuellement ENREGISTRÉ — pas le brouillon en cours de saisie. C'est à lui que les
   * réponses sont comparées, faute de savoir sous quel plafond chacune a été produite : les
   * messages persistés ne portent pas les paramètres de leur génération.
   */
  readonly plafond: number | null;
  /** Messages de la conversation, tels que le backend les a persistés. */
  readonly messages: readonly MessageChat[];
}

export function PlafondReponses({ plafond, messages }: PlafondReponsesProps): ReactElement {
  const bilan = bilanReponses(messages, plafond);
  // La mise en garde n'apparaît qu'avec le chiffre qu'elle qualifie : sans part de raisonnement
  // affichée, elle n'expliquerait rien et ferait du bruit.
  const raisonnementVu = (bilan.plusLongue?.raisonnement.caracteres ?? 0) > 0;
  return (
    <div className="space-y-1.5 rounded-sm border border-border px-3 py-2">
      <Mecanisme plafond={plafond} />
      <Constat bilan={bilan} plafond={plafond} />
      {raisonnementVu && (
        <p className="text-2xs leading-snug text-text-3">
          Des caractères, pas des jetons : la part du raisonnement en jetons est mesurée par le
          panneau de contexte, avec le tokenizer du modèle chargé.
        </p>
      )}
    </div>
  );
}
