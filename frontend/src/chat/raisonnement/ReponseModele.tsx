import { useMemo } from 'react';
import type { ReactElement } from 'react';
import { CarteArtefact, artefactDepuisSegment } from '../artefacts';
import { RenduMarkdown } from '../markdown';
import { BlocRaisonnement } from './BlocRaisonnement';
import { segmenterReponse, type ReponseSegmentee, type SegmentRaisonnement } from './extraction';

/*
 * Une réponse de modèle telle qu'elle doit se lire : les blocs de raisonnement d'abord, repliés,
 * puis la réponse rendue en Markdown.
 *
 * Les blocs passent avant parce que c'est leur ordre d'émission, et parce qu'un bloc replié
 * n'occupe qu'une ligne : la réponse reste la première chose lisible de l'écran.
 *
 * Le cas « rien hors du raisonnement » est nommé au lieu d'être laissé vide. Il arrive pour de bon
 * sur les modèles de raisonnement dont le budget de génération s'épuise avant la réponse ; un
 * message blanc laisserait croire à une panne d'affichage.
 */

interface SansReponseProps {
  segmentee: ReponseSegmentee;
  actif: boolean;
}

function SansReponse({ segmentee, actif }: SansReponseProps): ReactElement | null {
  // Pendant la génération, « pas encore de réponse » n'est pas une information : le bloc de
  // raisonnement affiche déjà son activité.
  if (actif || segmentee.raisonnements.length === 0) {
    return null;
  }
  const dernier = segmentee.raisonnements[segmentee.raisonnements.length - 1];
  const coupe = dernier !== undefined && !dernier.complet;
  return (
    <p className="text-xs text-caution">
      {coupe
        ? "La génération s'est arrêtée en plein raisonnement : aucune réponse n'a été écrite."
        : "Le modèle n'a rien écrit en dehors de son raisonnement."}
    </p>
  );
}

export interface ReponseModeleProps {
  source: string;
  /**
   * `true` pendant le streaming. Sert uniquement à distinguer un bloc qui grandit d'un bloc figé :
   * l'analyse du texte ne peut pas le savoir, et une animation le prétendrait à tort.
   */
  actif?: boolean;
}

/*
 * Un artefact présenté (`presenter_fichier`) se lit comme la réponse elle-même, pas comme un
 * appel d'outil ordinaire : il sort donc du traitement replié de `BlocRaisonnement` et s'affiche
 * en carte, directement visible dans le fil — c'est tout l'objet de l'outil (plan d'exécution,
 * lot L3), le faire voir plutôt que le laisser dans un bloc que l'utilisateur doit déplier.
 */
interface SegmentOuArtefactProps {
  segment: SegmentRaisonnement;
  rang: number | null;
  actif: boolean;
}

function SegmentOuArtefact({ segment, rang, actif }: SegmentOuArtefactProps): ReactElement {
  const artefact = artefactDepuisSegment(segment);
  if (artefact !== null) {
    return <CarteArtefact artefact={artefact} />;
  }
  return <BlocRaisonnement segment={segment} rang={rang} actif={actif} />;
}

export function ReponseModele({ source, actif = false }: ReponseModeleProps): ReactElement {
  // Le streaming remplace `source` à chaque fragment : la séparation est mémoïsée sur le texte reçu.
  const segmentee = useMemo(() => segmenterReponse(source), [source]);
  // Les blancs qui encadrent la réponse (après `</think>`, typiquement deux sauts de ligne) ne
  // portent rien : les retirer distingue une réponse vide d'une réponse faite de deux retours.
  const visible = segmentee.visible.trim();
  const multiples = segmentee.raisonnements.length > 1;
  return (
    <div className="space-y-2">
      {segmentee.raisonnements.map((segment, index) => (
        <SegmentOuArtefact
          key={index}
          segment={segment}
          rang={multiples ? index + 1 : null}
          actif={actif && !segment.complet}
        />
      ))}
      {visible !== '' ? (
        <RenduMarkdown source={visible} />
      ) : (
        <SansReponse segmentee={segmentee} actif={actif} />
      )}
    </div>
  );
}
