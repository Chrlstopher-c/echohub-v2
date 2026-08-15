import type { ReactElement } from 'react';
import { Badge, Button, Card } from '../shared/design';
import { Contraintes } from './contraintes/Contraintes';
import { heure } from './format';
import { Materiel } from './materiel/Materiel';
import { useProfilMachine, type EtatProfil } from './materiel/useProfilMachine';
import { Moteurs } from './moteurs/Moteurs';

/*
 * Écran Système — ce que la machine EST, et ce qu'elle interdit.
 *
 * Trois blocs dans cet ordre, qui est celui du raisonnement : le matériel mesuré, les contraintes
 * que la plateforme impose par-dessus, puis les moteurs qui devront s'en accommoder.
 */

function EnTete({ profil }: { profil: EtatProfil }): ReactElement {
  const mesure = profil.donnee !== null ? heure(profil.donnee.mesure_le) : null;
  return (
    <header className="mb-4 flex flex-wrap items-baseline justify-between gap-3 lg:mb-6">
      <div>
        <h1 className="text-xl font-semibold text-text">Système</h1>
        <p className="mt-1 text-xs text-text-2">
          Chaque valeur affichée ici est relue à la demande. Rien n&apos;est mémorisé : un profil ancien
          décrirait la machine telle qu&apos;elle était.
        </p>
      </div>
      <div className="flex items-center gap-2">
        {mesure !== null && !profil.suspendu && (
          <Badge tone="accent" pulse>
            mesure de {mesure}
          </Badge>
        )}
        <Button size="sm" onClick={profil.rafraichir} loading={profil.chargement}>
          Rafraîchir
        </Button>
      </div>
    </header>
  );
}

function Indisponible({ profil }: { profil: EtatProfil }): ReactElement {
  return (
    <Card title="Profil matériel indisponible">
      <p className="text-xs text-text-2">{profil.erreur ?? 'Mesure en cours…'}</p>
      {profil.suspendu && (
        <p className="mt-2 text-2xs text-text-3">
          Le sondage s&apos;est arrêté après plusieurs échecs consécutifs. Il ne repartira pas tout seul.
        </p>
      )}
    </Card>
  );
}

export function EcranSysteme(): ReactElement {
  const profil = useProfilMachine();

  return (
    // La marge sûre porte les 16 px de base ; `lg:px-2` rétablit exactement les 24 px d'origine.
    <div className="eh-marge-sure-x">
      <div className="mx-auto max-w-5xl py-6 lg:px-2 lg:py-8">
        <EnTete profil={profil} />

        {profil.donnee === null ? (
          <Indisponible profil={profil} />
        ) : (
          <div className="space-y-4 lg:space-y-6">
            {profil.erreur !== null && (
              <p className="rounded-xs bg-caution-soft px-2 py-1.5 text-2xs text-caution">
                Dernière mesure échouée ({profil.erreur}) — les valeurs ci-dessous datent de la précédente.
              </p>
            )}
            <Materiel profil={profil.donnee} />
            <Contraintes contraintes={profil.donnee.contraintes} avertissements={profil.donnee.avertissements} />
            <Moteurs />
          </div>
        )}
      </div>
    </div>
  );
}
