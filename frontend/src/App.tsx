import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

import { EcranChat } from './chat';
import { EcranModeles } from './models';
import { EcranSysteme } from './system';
import { Button, cn, fadeUp, TONE_VAR, transitionBase, type Tone } from './shared/design';
import { lireEtatInference, type EtatChargement, type StatutInference } from './shared/api';

/*
 * Mise en page générale et navigation entre les trois écrans du MVP.
 *
 * Contrat avec les domaines : chaque dossier d'écran expose SON composant depuis son `index.ts`
 * (`models` -> `EcranModeles`, `chat` -> `EcranChat`, `system` -> `EcranSysteme`). Rien d'autre
 * n'est importé d'eux — App ne connaît ni leurs hooks, ni leurs sous-composants.
 *
 * L'état d'inférence est affiché ici, dans le bandeau, parce qu'il est vrai pour toute
 * l'application : le GPU est une ressource exclusive, un seul modèle est chargé à la fois. Le
 * savoir depuis n'importe quel écran évite de retourner sur Système pour comprendre pourquoi une
 * génération refuse de démarrer.
 */

type Ecran = 'modeles' | 'chat' | 'systeme';

type Theme = 'dark' | 'light';

const ONGLETS: readonly { readonly cle: Ecran; readonly libelle: string }[] = [
  { cle: 'modeles', libelle: 'Modèles' },
  { cle: 'chat', libelle: 'Chat' },
  { cle: 'systeme', libelle: 'Système' },
];

/** Le bandeau reflète l'état réel : il sonde, il ne suppose pas ce qu'un écran a pu déclencher. */
const INTERVALLE_ETAT_MS = 5_000;

const CLE_THEME = 'echohub.theme';

const TONE_ETAT: Record<EtatChargement, Tone> = {
  inactif: 'neutral',
  en_cours: 'accent',
  pret: 'ok',
  echoue: 'critical',
};

const LIBELLE_ETAT: Record<EtatChargement, string> = {
  inactif: 'aucun modèle',
  en_cours: 'chargement',
  pret: 'prêt',
  echoue: 'échec',
};

function lireThemeInitial(): Theme {
  try {
    const stocke = window.localStorage.getItem(CLE_THEME);
    return stocke === 'light' || stocke === 'dark' ? stocke : 'dark';
  } catch (cause) {
    // Stockage refusé (navigation privée, politique de site) : le thème sombre reste le défaut.
    console.warn('Préférence de thème illisible :', cause);
    return 'dark';
  }
}

function useTheme(): readonly [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(lireThemeInitial);
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      window.localStorage.setItem(CLE_THEME, theme);
    } catch (cause) {
      console.warn('Préférence de thème non enregistrée :', cause);
    }
  }, [theme]);
  const basculer = useCallback((): void => {
    setTheme((actuel) => (actuel === 'dark' ? 'light' : 'dark'));
  }, []);
  return [theme, basculer];
}

/** Sondage borné par le démontage du composant ; chaque requête porte en plus son propre délai. */
function useEtatInference(): StatutInference | null {
  const [statut, setStatut] = useState<StatutInference | null>(null);
  useEffect(() => {
    const controleur = new AbortController();
    let monte = true;
    const sonder = async (): Promise<void> => {
      try {
        const prochain = await lireEtatInference(controleur.signal);
        if (monte) setStatut(prochain);
      } catch (cause) {
        // Un backend injoignable rend l'état inconnu ; il ne doit pas faire tomber l'interface.
        if (monte) setStatut(null);
        console.warn("État d'inférence indisponible :", cause);
      }
    };
    void sonder(); // premier relevé immédiat, la promesse est volontairement non attendue ici
    const minuterie = window.setInterval(() => void sonder(), INTERVALLE_ETAT_MS);
    return () => {
      monte = false;
      window.clearInterval(minuterie);
      controleur.abort();
    };
  }, []);
  return statut;
}

function Marque(): ReactElement {
  return (
    <div className="flex items-center gap-2 pr-2">
      <span className="text-md font-semibold tracking-tight">EchoHub</span>
      <span className="font-mono text-2xs text-text-3">v2</span>
    </div>
  );
}

interface OngletProps {
  readonly libelle: string;
  readonly actif: boolean;
  readonly onClick: () => void;
}

function Onglet({ libelle, actif, onClick }: OngletProps): ReactElement {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={actif}
      onClick={onClick}
      className={cn(
        'relative h-12 px-3 text-sm font-medium transition-colors duration-fast ease-out',
        'focus-visible:outline-none focus-visible:shadow-[inset_0_0_0_2px_var(--ring)]',
        actif ? 'text-text' : 'text-text-2 hover:text-text',
      )}
    >
      {libelle}
      {actif && (
        // Le trait suit l'onglet actif : la continuité du mouvement dit d'où l'on vient.
        <motion.span
          layoutId="onglet-actif"
          transition={transitionBase}
          className="absolute inset-x-2 bottom-0 h-px bg-accent"
        />
      )}
    </button>
  );
}

function EtatInference({ statut }: { readonly statut: StatutInference | null }): ReactElement {
  const etat: EtatChargement = statut?.etat ?? 'inactif';
  const modele = statut?.modele ?? null;
  const inconnu = statut === null;
  return (
    <div className="flex items-center gap-2" title={statut?.message ?? undefined}>
      <span
        aria-hidden="true"
        className={cn('h-1.5 w-1.5 rounded-full', etat === 'en_cours' && 'animate-eh-pulse')}
        style={{ background: inconnu ? TONE_VAR.neutral : TONE_VAR[TONE_ETAT[etat]] }}
      />
      <span className="text-xs text-text-2">{inconnu ? 'backend injoignable' : LIBELLE_ETAT[etat]}</span>
      {modele !== null && <span className="max-w-[14rem] truncate font-mono text-xs text-text-3">{modele}</span>}
    </div>
  );
}

// Icônes monochromes, trait 1,5 px (DESIGN.md). Les rayons du soleil sont découpés en deux
// chemins pour rester lisibles dans la limite de longueur de ligne.
const TRAIT = { stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' } as const;
const RAYONS_CARDINAUX = 'M8 1.5v1.2M8 13.3v1.2M14.5 8h-1.2M2.7 8H1.5';
const RAYONS_DIAGONAUX = 'M12.6 3.4l-.8.8M4.2 11.8l-.8.8M12.6 12.6l-.8-.8M4.2 4.2l-.8-.8';

function IconeTheme({ theme }: { readonly theme: Theme }): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden="true">
      {theme === 'dark' ? (
        <path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5Z" {...TRAIT} strokeLinejoin="round" />
      ) : (
        <>
          <circle cx="8" cy="8" r="3" {...TRAIT} />
          <path d={RAYONS_CARDINAUX} {...TRAIT} />
          <path d={RAYONS_DIAGONAUX} {...TRAIT} />
        </>
      )}
    </svg>
  );
}

function rendreEcran(ecran: Ecran): ReactElement {
  switch (ecran) {
    case 'modeles':
      return <EcranModeles />;
    case 'chat':
      return <EcranChat />;
    case 'systeme':
      return <EcranSysteme />;
  }
}

export function App(): ReactElement {
  const [ecran, setEcran] = useState<Ecran>('modeles');
  const [theme, basculerTheme] = useTheme();
  const statut = useEtatInference();

  return (
    <div className="flex h-screen flex-col bg-bg text-text">
      <header className="flex h-12 shrink-0 items-center gap-1 border-b border-border px-4">
        <Marque />
        <nav role="tablist" aria-label="Écrans" className="flex items-center">
          {ONGLETS.map((onglet) => (
            <Onglet
              key={onglet.cle}
              libelle={onglet.libelle}
              actif={onglet.cle === ecran}
              onClick={() => setEcran(onglet.cle)}
            />
          ))}
        </nav>
        <div className="flex flex-1 items-center justify-end gap-3">
          <EtatInference statut={statut} />
          <Button
            variant="ghost"
            size="sm"
            onClick={basculerTheme}
            aria-label={theme === 'dark' ? 'Passer au thème clair' : 'Passer au thème sombre'}
          >
            <IconeTheme theme={theme} />
          </Button>
        </div>
      </header>

      <main className="min-h-0 flex-1">
        {/* `mode="wait"` : le nouvel écran n'entre qu'une fois l'ancien sorti — deux écrans
            superposés donneraient deux jeux de mesures visibles en même temps. */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={ecran}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="h-full overflow-y-auto"
          >
            {rendreEcran(ecran)}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
