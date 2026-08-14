import type { ReactElement } from 'react';
import { Badge, Button } from '../shared/design';
import { FournisseurActions, useActionsFil, type EtatActionsFil } from './actions';
import { PanneauContexte } from './contexte';
import { Composeur } from './conversation/Composeur';
import { FilMessages } from './conversation/FilMessages';
import { ListeConversations } from './conversation/ListeConversations';
import { ModaleReglages } from './reglages';
import { PanneauPlan } from './plan/PanneauPlan';
import type { CibleChargement } from './plan/cible';
import { useEcranChat, type EtatEcranChat } from './useEcranChat';

/*
 * Écran de conversation. Trois colonnes : les conversations, l'échange, et le plan de chargement.
 *
 * Le plan occupe une colonne permanente plutôt qu'une modale : ce n'est pas une étape qu'on
 * traverse avant de discuter, c'est l'état de la machine pendant qu'on discute. Le débit mesuré de
 * la dernière réponse remonte d'ailleurs du fil vers le plan — la conversation devient la mesure.
 */

interface EnTeteProps {
  titre: string;
  modele: string | null;
  pret: boolean;
  onReglages: () => void;
}

function EnTeteChat({ titre, modele, pret, onReglages }: EnTeteProps): ReactElement {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
      <div className="min-w-0">
        <h1 className="truncate text-md font-semibold text-text">{titre}</h1>
        {modele !== null && <p className="truncate text-2xs text-text-3">{modele}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge tone={pret ? 'ok' : 'neutral'} dot>
          {pret ? 'moteur prêt' : 'moteur inactif'}
        </Badge>
        <Button variant="ghost" size="sm" onClick={onReglages}>
          Réglages
        </Button>
      </div>
    </header>
  );
}

function FilVide({ cible }: { cible: CibleChargement | null }): ReactElement {
  return (
    <div className="mx-auto flex h-full max-w-md flex-col justify-center text-center">
      <p className="text-sm leading-relaxed text-text-2">
        {cible === null
          ? 'Sélectionnez un modèle pour voir le plan de chargement calculé pour cette machine.'
          : 'Le plan est calculé à droite. Chargez le modèle, puis écrivez votre premier message.'}
      </p>
    </div>
  );
}

function empechementSaisie(conversationChoisie: boolean, moteurPret: boolean): string {
  if (!conversationChoisie) {
    return 'Créez une conversation pour commencer.';
  }
  if (!moteurPret) {
    return 'Aucun modèle prêt : chargez-en un depuis le plan, à droite.';
  }
  return '';
}

interface ColonneProps {
  etat: EtatEcranChat;
  cible: CibleChargement | null;
}

interface ColonneEchangeProps extends ColonneProps {
  fil: EtatActionsFil;
}

function ColonneEchange({ etat, cible, fil }: ColonneEchangeProps): ReactElement {
  const { courante, conversationActive, moteurPret } = etat;
  // Deux flux peuvent alimenter le fil : le composeur et un rejeu lancé depuis un message. Le
  // moteur n'en sert qu'un à la fois (le backend refuse le second), donc l'écran n'en montre qu'un.
  const genere = courante.genere || fil.genere;
  return (
    <section className="flex min-w-0 flex-1 flex-col">
      <EnTeteChat
        titre={courante.detail?.conversation.titre ?? 'Conversation'}
        modele={etat.chargement.statut?.modele ?? cible?.nomModele ?? null}
        pret={moteurPret}
        onReglages={() => etat.ouvrirReglages(true)}
      />
      <LigneErreur texte={courante.erreur ?? fil.erreur} />
      {/* `fil.messages` est le chemin de branche servi par le serveur ; tant qu'il n'est pas
          arrivé il vaut `null` et l'historique déjà chargé fait foi — aucun chemin n'est déduit. */}
      <FournisseurActions valeur={fil.actions}>
        <FilMessages
          messages={fil.messages ?? courante.messages}
          brouillon={fil.brouillon ?? courante.brouillon}
          vide={<FilVide cible={cible} />}
        />
      </FournisseurActions>
      <Composeur
        genere={genere}
        desactive={conversationActive === null || !moteurPret}
        empechement={empechementSaisie(conversationActive !== null, moteurPret)}
        onEnvoyer={(contenu) => envoyer(courante, fil, contenu)}
        onAnnuler={() => interrompre(courante, fil)}
      />
    </section>
  );
}

function LigneErreur({ texte }: { texte: string | null }): ReactElement | null {
  if (texte === null) {
    return null;
  }
  return <p className="border-b border-border px-6 py-2 text-xs text-critical">{texte}</p>;
}

/*
 * L'envoi est signalé aux deux états. Le fil de branche affiche le chemin servi par le serveur : il
 * ignore l'optimisme local de `useConversation`, et sans ce signal le message parti resterait
 * invisible jusqu'à la fin de la génération.
 */
function envoyer(courante: EtatEcranChat['courante'], fil: EtatActionsFil, contenu: string): void {
  fil.noterEnvoi(contenu);
  void courante.envoyer(contenu);
}

/* L'arrêt vise le tour réellement en cours ; chaque flux ignore la demande s'il n'a rien à couper. */
function interrompre(courante: EtatEcranChat['courante'], fil: EtatActionsFil): void {
  void courante.annuler();
  void fil.annuler();
}

/*
 * Le plan dit ce que le chargement a COÛTÉ ; le contexte dit ce que la conversation CONSOMME.
 * Les deux répondent à la même question — « pourquoi ça coince » — à deux instants différents,
 * d'où leur voisinage dans la même colonne.
 *
 * La conversion `contenu` -> `content` est nécessaire et non cosmétique : le domaine `chat`
 * persiste en français, le contrat des moteurs est en anglais. Compter les tokens exige la forme
 * qui repart réellement au modèle.
 */
function ColonnePlan({ etat, cible }: ColonneProps): ReactElement {
  const messagesMoteur = etat.courante.messages.map((message) => ({
    role: message.role,
    content: message.contenu,
  }));
  return (
    <aside className="flex w-[26rem] shrink-0 flex-col gap-3 overflow-y-auto border-l border-border p-3">
      <PanneauPlan
        cible={cible}
        etatPlan={etat.etatPlan}
        chargement={etat.chargement}
        debitObserve={etat.courante.debitObserve}
      />
      <PanneauContexte
        promptSysteme={etat.courante.detail?.reglages.prompt_systeme ?? ''}
        messages={messagesMoteur}
        modeleCharge={cible?.demande.metadonnees.identifiant ?? null}
        // Une génération en cours fait varier le décompte à chaque fragment : mesurer alors
        // coûterait une tokenisation par token reçu, sur le verrou du moteur qui génère.
        actif={!etat.courante.genere}
      />
    </aside>
  );
}

/*
 * Modale de réglages complète : prompt système, échantillonnage, plafond de réponse, séquences
 * d'arrêt. Elle remplace l'ancien panneau en lecture partielle — c'est elle qui adosse le plafond
 * de réponse aux mesures réelles de la conversation, ce que réclamait la troncature systématique
 * des réponses des modèles de raisonnement.
 */
function PanneauDeReglages({ etat }: { etat: EtatEcranChat }): ReactElement | null {
  const detail = etat.courante.detail;
  if (detail === null || etat.conversationActive === null) {
    return null;
  }
  return (
    <ModaleReglages
      ouvert={etat.reglagesOuverts}
      conversationId={etat.conversationActive}
      reglages={detail.reglages}
      messages={etat.courante.messages}
      onFermer={() => etat.ouvrirReglages(false)}
    />
  );
}

export interface ChatEcranProps {
  /**
   * Modèle sélectionné et entrées mesurées du planificateur, fournis par les domaines `models` et
   * `system`. La référence doit être stable entre deux rendus : elle déclenche la replanification.
   */
  cible: CibleChargement | null;
}

export function ChatEcran({ cible }: ChatEcranProps): ReactElement {
  const etat = useEcranChat(cible);
  // `courante.genere` est passé au fil de branche : c'est le seul signal qui dit qu'un tour occupe
  // déjà le moteur, et sa fin est le moment où la feuille active a pu changer sans qu'on l'ait
  // demandé — donc le moment où la vue de branche doit être relue.
  const fil = useActionsFil(etat.conversationActive, etat.courante.genere);
  return (
    <div className="flex h-full min-h-0 bg-bg">
      <ListeConversations
        conversations={etat.liste.conversations}
        conversationActive={etat.conversationActive}
        erreur={etat.liste.erreur}
        onOuvrir={etat.choisirConversation}
        onCreer={etat.creerConversation}
        onSupprimer={etat.supprimerConversation}
      />
      <ColonneEchange etat={etat} cible={cible} fil={fil} />
      <ColonnePlan etat={etat} cible={cible} />
      <PanneauDeReglages etat={etat} />
    </div>
  );
}
