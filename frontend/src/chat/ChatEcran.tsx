import type { ReactElement } from 'react';
import { Badge, Button } from '../shared/design';
import { Composeur } from './conversation/Composeur';
import { FilMessages } from './conversation/FilMessages';
import { ListeConversations } from './conversation/ListeConversations';
import { ReglagesConversation } from './conversation/ReglagesConversation';
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

function ColonneEchange({ etat, cible }: ColonneProps): ReactElement {
  const { courante, conversationActive, moteurPret } = etat;
  return (
    <section className="flex min-w-0 flex-1 flex-col">
      <EnTeteChat
        titre={courante.detail?.conversation.titre ?? 'Conversation'}
        modele={etat.chargement.statut?.modele ?? cible?.nomModele ?? null}
        pret={moteurPret}
        onReglages={() => etat.ouvrirReglages(true)}
      />
      {courante.erreur !== null && (
        <p className="border-b border-border px-6 py-2 text-xs text-critical">{courante.erreur}</p>
      )}
      <FilMessages
        messages={courante.messages}
        brouillon={courante.brouillon}
        vide={<FilVide cible={cible} />}
      />
      <Composeur
        genere={courante.genere}
        desactive={conversationActive === null || !moteurPret}
        empechement={empechementSaisie(conversationActive !== null, moteurPret)}
        onEnvoyer={(contenu) => void courante.envoyer(contenu)}
        onAnnuler={() => void courante.annuler()}
      />
    </section>
  );
}

function ColonnePlan({ etat, cible }: ColonneProps): ReactElement {
  return (
    <aside className="w-[26rem] shrink-0 overflow-y-auto border-l border-border p-3">
      <PanneauPlan
        cible={cible}
        etatPlan={etat.etatPlan}
        chargement={etat.chargement}
        debitObserve={etat.courante.debitObserve}
      />
    </aside>
  );
}

function ModaleReglages({ etat }: { etat: EtatEcranChat }): ReactElement | null {
  const detail = etat.courante.detail;
  if (detail === null) {
    return null;
  }
  return (
    <ReglagesConversation
      ouvert={etat.reglagesOuverts}
      reglages={detail.reglages}
      onFermer={() => etat.ouvrirReglages(false)}
      onEnregistrer={(patch) => void etat.courante.enregistrerReglages(patch)}
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
      <ColonneEchange etat={etat} cible={cible} />
      <ColonnePlan etat={etat} cible={cible} />
      <ModaleReglages etat={etat} />
    </div>
  );
}
