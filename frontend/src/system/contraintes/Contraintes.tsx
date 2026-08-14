import type { ReactElement } from 'react';
import { Badge, Card } from '../../shared/design';
import type { ContraintesPlateforme, SyntaxeGpuDocker } from '../api/types';

/*
 * Les contraintes de plateforme, rendues lisibles.
 *
 * C'est le seul écran du produit où le texte long est justifié : chaque contrainte porte la mesure
 * qui l'a établie, et cette mesure est affichée en entier. Cacher la justification derrière une
 * infobulle reviendrait à demander à l'utilisateur de croire l'application sur parole — or c'est
 * précisément la confiance aveugle dans des constantes non mesurées qui a coulé la v1.
 *
 * Le texte vient du backend (`ContraintesPlateforme.justifications`), indexé par nom de champ.
 * L'interface ne rédige rien : elle rend ce que la plateforme a répondu.
 */

const SYNTAXE_DOCKER: Record<SyntaxeGpuDocker, string> = {
  deploy_reservations: 'deploy.resources.reservations.devices',
  cdi: 'devices: ["nvidia.com/gpu=all"]',
};

interface LigneContrainte {
  cle: string;
  libelle: string;
  valeur: string;
  /** `true` quand la plateforme retire une possibilité : c'est un compromis, donc de l'ambre. */
  contraignante: boolean;
}

function lignes(contraintes: ContraintesPlateforme): LigneContrainte[] {
  return [
    {
      cle: 'memoire_unifiee_cuda',
      libelle: 'Mémoire unifiée CUDA',
      valeur: contraintes.memoire_unifiee_cuda ? 'disponible' : 'désactivée',
      contraignante: !contraintes.memoire_unifiee_cuda,
    },
    {
      cle: 'ram_plafonnee_par_hote',
      libelle: "RAM plafonnée par l'hôte",
      valeur: contraintes.ram_plafonnee_par_hote ? 'oui' : 'non',
      contraignante: contraintes.ram_plafonnee_par_hote,
    },
    {
      cle: 'pin_memory_disponible',
      libelle: 'Mémoire épinglée (pin_memory)',
      valeur: contraintes.pin_memory_disponible ? 'disponible' : 'indisponible',
      contraignante: !contraintes.pin_memory_disponible,
    },
    {
      cle: 'syntaxe_gpu_docker',
      libelle: 'Exposition du GPU à Docker',
      valeur: SYNTAXE_DOCKER[contraintes.syntaxe_gpu_docker],
      contraignante: false,
    },
  ];
}

function Ligne({ ligne, justification }: { ligne: LigneContrainte; justification?: string }): ReactElement {
  return (
    <li className="border-t border-border py-3 first:border-t-0 first:pt-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-text">{ligne.libelle}</span>
        <Badge tone={ligne.contraignante ? 'caution' : 'neutral'}>{ligne.valeur}</Badge>
      </div>
      {justification !== undefined && <p className="mt-1.5 text-xs leading-relaxed text-text-2">{justification}</p>}
    </li>
  );
}

function VariablesImposees({ variables }: { variables: Record<string, string> }): ReactElement | null {
  const entrees = Object.entries(variables);
  if (entrees.length === 0) {
    return null;
  }
  return (
    <div className="mt-4 border-t border-border pt-3">
      <p className="mb-2 text-xs text-text-2">
        Variables d&apos;environnement imposées au moteur. Elles sont posées explicitement, y compris à
        &laquo;&nbsp;0&nbsp;&raquo; : omettre la variable laisserait un environnement hérité réactiver le piège.
      </p>
      <ul className="space-y-1">
        {entrees.map(([nom, valeur]) => (
          <li key={nom} className="font-mono text-2xs tabular-nums text-text">
            {nom}=<span className="text-mem-kv">{valeur}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface ContraintesProps {
  contraintes: ContraintesPlateforme;
  avertissements: string[];
}

export function Contraintes({ contraintes, avertissements }: ContraintesProps): ReactElement {
  return (
    <Card title="Ce que la plateforme impose">
      <ul>
        {lignes(contraintes).map((ligne) => (
          <Ligne key={ligne.cle} ligne={ligne} justification={contraintes.justifications[ligne.cle]} />
        ))}
      </ul>
      <VariablesImposees variables={contraintes.variables_env_imposees} />
      {avertissements.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-border pt-3">
          {avertissements.map((message) => (
            <li key={message} className="rounded-xs bg-caution-soft px-2 py-1.5 text-2xs text-caution">
              {message}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
