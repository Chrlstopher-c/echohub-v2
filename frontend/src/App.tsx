import { Component, useCallback, useEffect, useState } from 'react';
import type { ErrorInfo, ReactElement, ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

import { ChatEcran } from './chat';
import { useCible } from './cible';
import { EcranModeles } from './models';
import { EcranSysteme } from './system';
import { Button, cn, fadeUp, TONE_VAR, transitionBase, type Tone } from './shared/design';
import { dechargerModele, lireEtatInference, type EtatChargement, type StatutInference } from './shared/api';

/*
 * Mise en page générale et navigation entre les trois écrans du MVP.
 *
 * Contrat avec les domaines : chaque dossier d'écran expose SON composant depuis son `index.ts`
 * (`models` -> `EcranModeles`, `chat` -> `ChatEcran`, `system` -> `EcranSysteme`). Rien d'autre
 * n'est importé d'eux — App ne connaît ni leurs hooks, ni leurs sous-composants.
 *
 * App est aussi le seul point de RENCONTRE des domaines : choisir un modèle dans `models` doit
 * produire une cible que `chat` sait planifier, et cela demande de croiser trois mesures. Ce
 * croisement est délégué à `cible/`, jamais fait ici ni dans un domaine — un domaine qui en
 * connaîtrait deux autres cesserait d'être remplaçable.
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
function useEtatInference(): readonly [StatutInference | null, () => void] {
  const [statut, setStatut] = useState<StatutInference | null>(null);
  // Incrémenté pour forcer un relevé hors du rythme de sondage — après une éjection, attendre
  // cinq secondes afficherait un état que l'utilisateur vient lui-même de rendre faux.
  const [reveil, setReveil] = useState(0);
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
  }, [reveil]);
  const resonder = useCallback((): void => setReveil((n) => n + 1), []);
  return [statut, resonder];
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

interface EtatInferenceProps {
  readonly statut: StatutInference | null;
  readonly onEjecter: () => void;
}

/*
 * Le GPU est exclusif : tant qu'un modèle l'occupe, aucun autre ne peut être chargé. L'éjection
 * appartient donc au bandeau, à côté de l'état — et pas à un écran, car elle est vraie partout.
 * Sans elle, un modèle chargé hors de cette page ne pouvait plus être libéré depuis l'interface.
 */
function EtatInference({ statut, onEjecter }: EtatInferenceProps): ReactElement {
  const etat: EtatChargement = statut?.etat ?? 'inactif';
  const modele = statut?.modele ?? null;
  const inconnu = statut === null;
  const [ejection, setEjection] = useState(false);

  const ejecter = useCallback((): void => {
    setEjection(true);
    void dechargerModele()
      .catch((cause: unknown) => console.warn('Éjection refusée :', cause))
      .finally(() => {
        setEjection(false);
        onEjecter();
      });
  }, [onEjecter]);

  return (
    <div className="flex items-center gap-2" title={statut?.message ?? undefined}>
      <span
        aria-hidden="true"
        className={cn('h-1.5 w-1.5 rounded-full', etat === 'en_cours' && 'animate-eh-pulse')}
        style={{ background: inconnu ? TONE_VAR.neutral : TONE_VAR[TONE_ETAT[etat]] }}
      />
      <span className="text-xs text-text-2">{inconnu ? 'backend injoignable' : LIBELLE_ETAT[etat]}</span>
      {modele !== null && <span className="max-w-[14rem] truncate font-mono text-xs text-text-3">{modele}</span>}
      {etat === 'pret' && (
        <Button variant="ghost" size="sm" onClick={ejecter} disabled={ejection} title="Libérer la VRAM">
          {ejection ? 'éjection…' : 'Éjecter'}
        </Button>
      )}
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

/** Refus d'assemblage : une métadonnée manque. Affiché tel quel — l'utilisateur peut agir dessus. */
function BandeauRefus({ refus }: { readonly refus: string }): ReactElement {
  return (
    <div className="border-b border-border px-4 py-2 text-xs" style={{ color: TONE_VAR.caution }}>
      {refus}
    </div>
  );
}

interface FrontiereProps {
  /** Écran affiché. Il change → la panne appartenait au précédent, la frontière rend la main. */
  readonly ecran: Ecran;
  readonly children: ReactNode;
}

interface EtatFrontiere {
  readonly panne: string | null;
}

/*
 * Filet de dernier recours autour de la zone de contenu.
 *
 * Sans lui, une exception levée pendant un rendu ou un effet de layout démonte l'arbre entier :
 * React 18 laisse alors une page noire, sans message ni trace, et seul un rechargement manuel la
 * ramène. C'est exactement ce que la doctrine du projet interdit — une absence à la place d'un
 * fait. Ici l'exception devient un texte affiché et une sortie possible.
 *
 * La frontière vit dans App et non dans un domaine : elle est vraie pour les trois écrans, aucun
 * ne peut la porter sans que les deux autres importent son interne. Elle enveloppe l'AnimatePresence
 * plutôt que chaque écran, pour couvrir aussi les effets de layout de framer-motion, qui sont au-
 * dessus des écrans.
 */
class FrontiereErreur extends Component<FrontiereProps, EtatFrontiere> {
  constructor(props: FrontiereProps) {
    super(props);
    this.state = { panne: null };
  }

  static getDerivedStateFromError(cause: unknown): EtatFrontiere {
    return { panne: cause instanceof Error ? cause.message : String(cause) };
  }

  override componentDidCatch(cause: Error, infos: ErrorInfo): void {
    console.error('Écran interrompu par une exception :', cause, infos.componentStack);
  }

  override componentDidUpdate(precedent: FrontiereProps): void {
    if (this.state.panne !== null && precedent.ecran !== this.props.ecran) {
      this.setState({ panne: null });
    }
  }

  override render(): ReactNode {
    if (this.state.panne === null) {
      return this.props.children;
    }
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <p className="text-sm text-text">L’écran s’est interrompu.</p>
        <p className="max-w-lg break-words font-mono text-xs text-text-3">{this.state.panne}</p>
        <Button variant="primary" size="sm" onClick={() => window.location.reload()}>
          Recharger
        </Button>
      </div>
    );
  }
}

export function App(): ReactElement {
  const [ecran, setEcran] = useState<Ecran>('modeles');
  const [theme, basculerTheme] = useTheme();
  const [statut, resonderEtat] = useEtatInference();
  const { cible, refus, erreur, choisir } = useCible();

  // Sélectionner un modèle amène sur le chat : c'est là que le plan est montré avant d'être appliqué.
  const surChoixModele = useCallback(
    (modele: Parameters<typeof choisir>[0]): void => {
      choisir(modele);
      setEcran('chat');
    },
    [choisir],
  );

  const rendreEcran = (): ReactElement => {
    switch (ecran) {
      case 'modeles':
        return <EcranModeles onCharger={surChoixModele} />;
      case 'chat':
        return <ChatEcran cible={cible} />;
      case 'systeme':
        return <EcranSysteme />;
    }
  };

  const alerte = refus === null ? erreur : `${refus.manquant} — ${refus.remediation}`;

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
          <EtatInference statut={statut} onEjecter={resonderEtat} />
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

      {alerte !== null && <BandeauRefus refus={alerte} />}

      {/* Une seule cellule de grille, partagée : les deux écrans s'y superposent le temps du
          fondu au lieu de s'empiler. C'est ce qui remplace `mode="wait"`, retiré parce qu'il
          laissait cette zone VIDE — donc noire — pendant la sortie de l'écran quitté, et
          définitivement vide si cette sortie ne s'achevait pas (démonter un arbre `layoutId`
          pendant la rafale de rendus d'une génération en cours). Le chevauchement dure 120 ms,
          le sortant déjà à `opacity: 0` : aucun risque de lire deux jeux de mesures à la fois. */}
      <main className="grid min-h-0 flex-1 grid-cols-1 grid-rows-1">
        <FrontiereErreur ecran={ecran}>
          <AnimatePresence initial={false}>
            <motion.div
              key={ecran}
              variants={fadeUp}
              initial="hidden"
              animate="visible"
              exit="exit"
              className="col-start-1 row-start-1 h-full min-h-0 overflow-y-auto"
            >
              {rendreEcran()}
            </motion.div>
          </AnimatePresence>
        </FrontiereErreur>
      </main>
    </div>
  );
}
