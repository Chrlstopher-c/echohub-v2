import type { ReactElement, ReactNode } from 'react';
import { Badge, Card } from '../../shared/design';
import type { Gpu, PiloteNvidia, Plateforme, ProfilMachine, SourceMesureGpu } from '../api/types';
import { entier, heure, octetsLisibles } from '../format';
import { BarreMemoire } from './BarreMemoire';
import { jauge, reference } from './echelle';

/*
 * Le matériel tel qu'il a été mesuré : GPU, mémoires à l'échelle réelle, plateforme, pilote.
 *
 * Rien n'est déduit ici. Chaque valeur affichée est un champ du profil, et l'instrument qui l'a
 * produite (NVML ou nvidia-smi) est indiqué : une mesure a une provenance.
 */

const LIBELLE_PLATEFORME: Record<Plateforme, string> = {
  wsl2: 'Windows + WSL2',
  linux_natif: 'Linux natif',
  windows: 'Windows',
  macos: 'macOS',
  inconnue: 'Non identifiée',
};

const LIBELLE_SOURCE: Record<SourceMesureGpu, string> = {
  nvml: 'NVML',
  nvidia_smi: 'nvidia-smi',
  aucune: 'aucun instrument',
};

function Ligne({ libelle, children }: { libelle: string; children: ReactNode }): ReactElement {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 py-1">
      <span className="shrink-0 text-xs text-text-2">{libelle}</span>
      {/* Sous `lg` la valeur se replie au lieu d'être coupée : rien n'est lisible au survol au doigt. */}
      <span className="min-w-0 break-all text-right font-mono text-xs tabular-nums text-text lg:truncate">
        {children}
      </span>
    </div>
  );
}

function DetailGpu({ gpu, source }: { gpu: Gpu; source: SourceMesureGpu }): ReactElement {
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="min-w-0 break-words text-md font-semibold text-text lg:truncate">{gpu.nom}</h3>
        {gpu.architecture_sm !== null && <Badge tone="vram">{gpu.architecture_sm}</Badge>}
      </div>
      <Ligne libelle="Capacité de calcul">
        {gpu.compute_majeur === null ? '—' : `${entier(gpu.compute_majeur)}.${entier(gpu.compute_mineur)}`}
      </Ligne>
      <Ligne libelle="Utilisation">{gpu.utilisation_pct === null ? '—' : `${entier(gpu.utilisation_pct)} %`}</Ligne>
      <Ligne libelle="Température">{gpu.temperature_c === null ? '—' : `${entier(gpu.temperature_c)} °C`}</Ligne>
      <Ligne libelle="Mesuré par">{LIBELLE_SOURCE[source]}</Ligne>
    </div>
  );
}

function AvertissementPilote({ gpu, pilote }: { gpu: Gpu | null; pilote: PiloteNvidia | null }): ReactElement | null {
  // Deux champs déjà calculés par le backend ; les rapprocher est de l'affichage, pas du calcul.
  if (gpu === null || !gpu.est_blackwell || pilote === null || pilote.supporte_blackwell) {
    return null;
  }
  return (
    <p className="mt-2 rounded-xs bg-critical-soft px-2 py-1.5 text-2xs text-critical">
      Pilote {pilote.version} en dessous du plancher 570 exigé par Blackwell. Le GPU ne sera pas exploitable
      tant que le pilote Windows n&apos;est pas relevé — sous WSL2, il ne s&apos;installe que côté Windows.
    </p>
  );
}

function CartePlateforme({ profil }: { profil: ProfilMachine }): ReactElement {
  return (
    <Card title="Plateforme">
      <Ligne libelle="Détectée">{LIBELLE_PLATEFORME[profil.plateforme]}</Ligne>
      <Ligne libelle="Pilote NVIDIA">{profil.pilote?.version ?? 'non lisible'}</Ligne>
      <Ligne libelle="Mesure">{heure(profil.mesure_le)}</Ligne>
      {/* Le `title` ne s'ouvre pas au doigt : sous `lg` la version du noyau est rendue en entier. */}
      <p className="mt-2 break-all text-2xs text-text-3 lg:truncate" title={profil.version_noyau}>
        {profil.version_noyau}
      </p>
      <AvertissementPilote gpu={profil.gpu_principal} pilote={profil.pilote} />
    </Card>
  );
}

function Memoires({ profil }: { profil: ProfilMachine }): ReactElement {
  const totalVram = profil.vram_totale_octets;
  const totalRam = profil.memoire?.totale_octets ?? 0;
  const commune = reference(totalVram, totalRam);
  const principal = profil.gpu_principal;
  return (
    <Card title="Mémoire" actions={<Badge tone="neutral">échelle réelle</Badge>}>
      <div className="space-y-4">
        <BarreMemoire
          libelle="VRAM"
          tone="vram"
          legende="Occupée par le système et les processus en cours"
          jauge={jauge(totalVram, principal?.vram_utilisee_octets ?? 0, commune)}
        />
        {profil.memoire === null ? (
          <p className="text-2xs text-text-3">
            RAM non mesurable sur cette machine. Aucun débordement en RAM ne peut être planifié à l&apos;aveugle.
          </p>
        ) : (
          <BarreMemoire
            libelle="RAM"
            tone="ram"
            legende="Occupée"
            jauge={jauge(totalRam, profil.memoire.utilisee_octets, commune)}
          />
        )}
        <p className="text-2xs text-text-3">
          Les deux barres partagent la même échelle : leur longueur compare des gigaoctets, pas des pourcentages.
        </p>
      </div>
    </Card>
  );
}

export function Materiel({ profil }: { profil: ProfilMachine }): ReactElement {
  const principal = profil.gpu_principal;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="GPU" actions={principal === null ? <Badge tone="critical">absent</Badge> : undefined}>
        {principal === null ? (
          <p className="text-xs text-text-2">
            Aucun GPU NVIDIA détecté. Tout chargement se fera sur processeur, à un débit sans rapport.
          </p>
        ) : (
          <DetailGpu gpu={principal} source={profil.source_gpu} />
        )}
        {profil.gpus.length > 1 && (
          <p className="mt-3 text-2xs text-text-3">
            {entier(profil.gpus.length)} GPU détectés. Le planificateur ne vise que le mieux doté :
            {` ${octetsLisibles(profil.vram_totale_octets)} de VRAM.`}
          </p>
        )}
      </Card>
      <Memoires profil={profil} />
      <CartePlateforme profil={profil} />
    </div>
  );
}
