/*
 * Interface publique du module `raisonnement` — seul point d'import autorisé depuis le reste du
 * domaine `chat`.
 *
 * Le module expose le composant qui rend une réponse complète (raisonnement séparé + Markdown) et
 * la fonction pure qui fait la séparation, pour qui aurait besoin du découpage sans le rendu (un
 * décompte, un export). Le bloc repliable et la table des conventions restent internes.
 */

export { ReponseModele, type ReponseModeleProps } from './ReponseModele';
export { segmenterReponse, type ReponseSegmentee, type SegmentRaisonnement } from './extraction';
