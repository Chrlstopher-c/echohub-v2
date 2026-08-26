/*
 * Colonne des conversations. La sélection se marque par une surface, pas par une bordure ni une
 * couleur d'accent : l'accent est réservé aux actions et à l'activité en cours.
 *
 * Chaque ligne porte sa mesure — nombre de messages et ancienneté, en mono tabulaire — à la
 * manière du panneau de plan : retrouver une conversation passe plus souvent par « celle d'hier »
 * que par son titre.
 *
 * Les actions (renommer, archiver, supprimer) vivent dans UN menu, au déclencheur permanent au
 * doigt et révélé au survol sur grand écran : le survol n'existe pas au doigt, une corbeille qui
 * n'apparaît qu'à lui y serait simplement absente. Les archivées restent accessibles dans une
 * section repliée en bas de colonne — chargée à l'ouverture, jamais avant.
 */

import { useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { BoutonActions, Button, cn, MenuContextuel, type EntreeMenu } from '../../shared/design';
import type { ResumeConversation } from '../api/contrats';
import { anciennete } from './temps';

function MetaLigne({ conversation }: { conversation: ResumeConversation }): ReactElement {
  return (
    <span className="flex items-baseline gap-x-1.5 font-mono text-2xs tabular-nums text-text-3">
      <span>{conversation.nb_messages} msg</span>
      <span aria-hidden="true">·</span>
      <span>{anciennete(conversation.maj_le)}</span>
    </span>
  );
}

/*
 * Renommage en place. Le champ prend EXACTEMENT la place du titre : mêmes marges, même taille de
 * texte, et la ligne de mesures reste dessous. Un champ de formulaire ordinaire romprait la
 * colonne — l'utilisateur doit voir le titre devenir modifiable, pas voir la ligne être remplacée
 * par autre chose.
 *
 * L'état de saisie se marque par la surface active de la ligne et une bordure de la même famille
 * que le reste, jamais par un anneau de focus épais : la ligne fait 3 mm de haut, un anneau de 2 px
 * y devient la forme dominante.
 */
function ChampTitre({ valeur, onValider, onAnnuler }: {
  valeur: string;
  onValider: (titre: string) => void;
  onAnnuler: () => void;
}): ReactElement {
  const [texte, setTexte] = useState(valeur);
  const champ = useRef<HTMLInputElement>(null);
  useEffect(() => champ.current?.select(), []);
  const valider = (): void => {
    const propre = texte.trim();
    if (propre !== '' && propre !== valeur) onValider(propre);
    else onAnnuler();
  };
  return (
    <input
      ref={champ}
      value={texte}
      onChange={(e) => setTexte(e.target.value)}
      onBlur={valider}
      onKeyDown={(e) => {
        if (e.key === 'Enter') valider();
        if (e.key === 'Escape') onAnnuler();
      }}
      className={cn(
        'w-full rounded-[3px] border border-accent bg-bg px-1 py-0 text-xs text-text',
        'focus:outline-none',
      )}
      aria-label="Renommer la conversation"
    />
  );
}

interface EntreeProps {
  conversation: ResumeConversation;
  active: boolean;
  onOuvrir: () => void;
  onSupprimer: () => void;
  onRenommer: (titre: string) => void;
  onArchiver: (archivee: boolean) => void;
}

function entreesMenu(
  props: EntreeProps,
  demarrerRenommage: () => void,
): EntreeMenu[] {
  const { conversation, active } = props;
  const archivee = conversation.archivee;
  return [
    { libelle: 'Ouvrir', onChoisir: props.onOuvrir, desactivee: active },
    { libelle: 'Renommer', onChoisir: demarrerRenommage },
    // Un seul verbe visible à la fois : « Archiver » range, « Désarchiver » restaure. Les deux
    // dans le même menu laisseraient croire à deux états simultanés.
    archivee
      ? { libelle: 'Désarchiver', onChoisir: () => props.onArchiver(false) }
      : { libelle: 'Archiver', onChoisir: () => props.onArchiver(true) },
    { libelle: 'Copier le titre', onChoisir: () => void navigator.clipboard?.writeText(conversation.titre) },
    { libelle: 'Supprimer', onChoisir: props.onSupprimer, destructive: true },
  ];
}

function LigneRenommage({ props, terminer }: { props: EntreeProps; terminer: () => void }): ReactElement {
  // Même enveloppe que la ligne normale — surface active, marges et interligne identiques — pour
  // que seule la nature du titre change, pas la géométrie de la colonne.
  return (
    <li className="relative list-none rounded-sm bg-surface-2 px-2 py-1.5">
      <ChampTitre
        valeur={props.conversation.titre}
        onValider={(titre) => {
          props.onRenommer(titre);
          terminer();
        }}
        onAnnuler={terminer}
      />
      <MetaLigne conversation={props.conversation} />
    </li>
  );
}

function LigneConversation({ props }: { props: EntreeProps }): ReactElement {
  const { conversation, active } = props;
  return (
    <button
      type="button"
      onClick={props.onOuvrir}
      className={cn(
        'min-w-0 flex-1 rounded-sm px-2 py-1.5 text-left transition-colors duration-fast',
        active ? 'bg-surface-2 text-text' : 'text-text-2 hover:bg-surface-2 hover:text-text',
        // Une archivée reste lisible mais en retrait : elle a été rangée, pas ouverte.
        conversation.archivee && !active && 'text-text-3',
      )}
    >
      <span className="block truncate text-xs">{conversation.titre}</span>
      <MetaLigne conversation={conversation} />
    </button>
  );
}

function Entree(props: EntreeProps): ReactElement {
  const [renomme, setRenomme] = useState(false);
  if (renomme) {
    return <LigneRenommage props={props} terminer={() => setRenomme(false)} />;
  }
  return (
    <MenuContextuel entrees={entreesMenu(props, () => setRenomme(true))} className="group relative block">
      {({ ouvrirDepuis }) => (
        <li className="relative flex list-none items-center">
          <LigneConversation props={props} />
          {/* Permanent au doigt ; sur grand écran il reste révélé au survol (ou au focus clavier) —
              la densité de la colonne est intacte. */}
          <BoutonActions
            libelle="Actions sur la conversation"
            onClick={(evenement) => ouvrirDepuis(evenement.currentTarget)}
            className={cn(
              'lg:pointer-events-none lg:opacity-0',
              'lg:group-hover:pointer-events-auto lg:group-hover:opacity-100',
              'lg:focus-visible:pointer-events-auto lg:focus-visible:opacity-100',
            )}
          />
        </li>
      )}
    </MenuContextuel>
  );
}

interface SectionArchiveesProps {
  archivees: ResumeConversation[] | null;
  conversationActive: string | null;
  onChargerArchivees: () => void;
  entree: (conversation: ResumeConversation) => ReactElement;
}

/*
 * Les archivées ne se mélangent jamais aux actives : la colonne sert le travail en cours, la
 * section du bas sert la mémoire. Le premier dépliage déclenche le chargement — d'où le compte
 * absent tant qu'on n'a pas ouvert : afficher « (0) » avant d'avoir demandé serait un mensonge.
 */
function SectionArchivees({ archivees, onChargerArchivees, entree }: SectionArchiveesProps): ReactElement {
  const [ouverte, setOuverte] = useState(false);
  const basculer = (): void => {
    if (!ouverte && archivees === null) {
      onChargerArchivees();
    }
    setOuverte(!ouverte);
  };
  return (
    <div className="shrink-0 border-t border-border px-2 py-2">
      <button
        type="button"
        onClick={basculer}
        aria-expanded={ouverte}
        className={cn(
          'flex w-full items-baseline gap-1.5 rounded-sm px-2 py-1 text-left text-2xs font-medium',
          'uppercase tracking-wide text-text-3 transition-colors duration-fast hover:text-text-2',
        )}
      >
        <span>{ouverte ? '▾' : '▸'}</span>
        <span>Archivées</span>
        {archivees !== null && (
          <span className="font-mono tabular-nums normal-case">{archivees.length}</span>
        )}
      </button>
      {ouverte && <ListeArchivees archivees={archivees} entree={entree} />}
    </div>
  );
}

function ListeArchivees({
  archivees,
  entree,
}: Pick<SectionArchiveesProps, 'archivees' | 'entree'>): ReactElement {
  return (
    <ul className="mt-0.5 max-h-48 space-y-0.5 overflow-y-auto">
      {archivees === null && <li className="px-2 py-1 text-2xs text-text-3">Chargement…</li>}
      {archivees !== null && archivees.length === 0 && (
        <li className="px-2 py-1 text-2xs text-text-3">Aucune conversation archivée.</li>
      )}
      {archivees?.map((conversation) => entree(conversation))}
    </ul>
  );
}

export interface ListeConversationsProps {
  conversations: ResumeConversation[];
  archivees: ResumeConversation[] | null;
  conversationActive: string | null;
  erreur: string | null;
  onOuvrir: (id: string) => void;
  onCreer: () => void;
  onSupprimer: (id: string) => void;
  onRenommer: (id: string, titre: string) => void;
  onArchiver: (id: string, archivee: boolean) => void;
  onChargerArchivees: () => void;
}

function EnTeteListe({ onCreer, erreur }: { onCreer: () => void; erreur: string | null }): ReactElement {
  return (
    <>
      <div className="flex items-center gap-2 px-3 py-3">
        {/* Le titre est déjà porté par l'entête du tiroir sous le seuil — le répéter volerait une
            ligne sur un écran qui n'en a pas de trop. */}
        <h2 className="hidden text-xs font-medium uppercase tracking-wide text-text-3 lg:block">Conversations</h2>
        <Button variant="secondary" size="sm" className="ml-auto" onClick={onCreer}>
          Nouvelle
        </Button>
      </div>
      {erreur !== null && <p className="px-3 pb-2 text-2xs text-critical">{erreur}</p>}
    </>
  );
}

export function ListeConversations(props: ListeConversationsProps): ReactElement {
  const { conversations, archivees, conversationActive, erreur } = props;
  const entree = (conversation: ResumeConversation): ReactElement => (
    <Entree
      key={conversation.id}
      conversation={conversation}
      active={conversation.id === conversationActive}
      onOuvrir={() => props.onOuvrir(conversation.id)}
      onSupprimer={() => props.onSupprimer(conversation.id)}
      onRenommer={(titre) => props.onRenommer(conversation.id, titre)}
      onArchiver={(archivee) => props.onArchiver(conversation.id, archivee)}
    />
  );
  return (
    // Dans le tiroir, la largeur et la bordure viennent du panneau : `w-60` y créerait une colonne
    // de 240 px dans un panneau de 320, avec un vide à droite.
    <nav
      className={cn(
        'flex h-full w-full min-w-0 flex-col bg-surface',
        'lg:w-60 lg:shrink-0 lg:border-r lg:border-border',
      )}
    >
      <EnTeteListe onCreer={props.onCreer} erreur={erreur} />
      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto overflow-x-hidden px-2 pb-3">
        {conversations.map((conversation) => entree(conversation))}
      </ul>
      <SectionArchivees
        archivees={archivees}
        conversationActive={conversationActive}
        onChargerArchivees={props.onChargerArchivees}
        entree={entree}
      />
    </nav>
  );
}
