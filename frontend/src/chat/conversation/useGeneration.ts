/*
 * Génération en streaming : ouverture du flux, accumulation du texte reçu, annulation.
 *
 * Séparé de la persistance parce que ce sont deux durées de vie différentes : l'historique survit
 * à la page, le flux ne survit pas au démontage — il est explicitement coupé.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { messageErreur } from '../api/client';
import type { EvenementFlux } from '../api/contrats';
import { annulerGeneration } from '../api/conversations-api';
import { ouvrirFluxGeneration } from '../api/flux-generation';
import { journal } from '../api/journal';

export interface EtatGeneration {
  /** Texte reçu jusqu'ici pour la réponse en cours ; `null` hors génération. */
  brouillon: string | null;
  genere: boolean;
  erreur: string | null;
  envoyer: (contenu: string) => Promise<void>;
  annuler: () => Promise<void>;
}

/**
 * @param onTermine relecture de l'historique persisté à la fermeture du flux. Le backend porte
 * l'identifiant réel du message, son débit mesuré et son éventuelle interruption : les reconstruire
 * à partir des fragments reviendrait à afficher une estimation.
 */
export function useGeneration(
  conversationId: string | null,
  onTermine: (conversationId: string) => Promise<void>,
): EtatGeneration {
  const [brouillon, setBrouillon] = useState<string | null>(null);
  const [genere, setGenere] = useState<boolean>(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const controleur = useRef<AbortController | null>(null);

  const traiter = useCallback((evenement: EvenementFlux): void => {
    if (evenement.type === 'fragment') {
      setBrouillon((texte) => (texte ?? '') + evenement.texte);
      return;
    }
    if (evenement.type === 'erreur') {
      setErreur(`${evenement.message} ${evenement.remediation}`.trim());
    }
    // `debut` et `fin` ne sont pas rendus : l'état persisté est relu à la fermeture du flux.
  }, []);

  const envoyer = useCallback(
    async (contenu: string): Promise<void> => {
      if (conversationId === null || genere) {
        return;
      }
      const controle = new AbortController();
      controleur.current = controle;
      setBrouillon('');
      setGenere(true);
      setErreur(null);
      try {
        await ouvrirFluxGeneration(conversationId, { contenu }, { onEvenement: traiter }, controle.signal);
      } catch (cause) {
        if (!controle.signal.aborted) {
          journal.erreur('génération interrompue', cause);
          setErreur(messageErreur(cause));
        }
      } finally {
        controleur.current = null;
        setGenere(false);
        setBrouillon(null);
        await onTermine(conversationId);
      }
    },
    [conversationId, genere, traiter, onTermine],
  );

  const annuler = useCallback(async (): Promise<void> => {
    if (conversationId === null) {
      return;
    }
    // Le serveur d'abord : il persiste le partiel et marque le message interrompu. Couper le flux
    // en premier laisserait la génération continuer côté moteur, VRAM occupée pour rien.
    try {
      await annulerGeneration(conversationId);
    } catch (cause) {
      journal.erreur('annulation refusée par le backend', cause);
    }
    controleur.current?.abort();
  }, [conversationId]);

  useEffect((): (() => void) => (): void => controleur.current?.abort(), []);

  return { brouillon, genere, erreur, envoyer, annuler };
}
