/*
 * Tests purs de la détection et du catalogue des artefacts versionnés.
 *
 * Lancement : `bun run frontend/src/chat/artefacts/tests/versions.test.ts`
 * Ils consomment les MÊMES textes d'exemple que la page de démonstration : ce que la capture
 * montre est ce que le test vérifie — un seul jeu de données, pas deux vérités.
 *
 * Harnais recopié localement, comme dans `markdown/tests` et `raisonnement/tests` (même raison).
 */

import { MESSAGES_ARTEFACT } from '../../conversation/demo/exemples';
import { versionDepuisAppel } from '../detection';
import { collecterArtefacts } from '../versions';

let echecs = 0;

function verifier(nom: string, obtenu: unknown, attendu: unknown): void {
  const gauche = JSON.stringify(obtenu);
  const droite = JSON.stringify(attendu);
  if (gauche === droite) {
    console.log(`ok    ${nom}`);
    return;
  }
  echecs += 1;
  console.error(`ÉCHEC ${nom}\n  obtenu  : ${gauche}\n  attendu : ${droite}`);
}

/* ---- collecte sur les messages d'exemple : deux artefacts, versions ordonnées ---- */
{
  const catalogue = collecterArtefacts(MESSAGES_ARTEFACT, null);
  verifier('catalogue — deux artefacts', catalogue.size, 2);
  const pong = catalogue.get('art-pong');
  verifier('pong — deux versions', pong?.versions.map((v) => v.version), [1, 2]);
  verifier('pong — titre de la dernière', pong?.titre, 'Pong néon');
  verifier('pong — type', pong?.type, 'html');
  verifier('notes — une version', catalogue.get('art-notes')?.versions.length, 1);
}

/* ---- une version refermée dans le BROUILLON est déjà ouvrable ---- */
{
  const brouillon =
    '<outil><entree>creer_artefact(titre : Brouillon, type : svg)</entree><sortie>' +
    '{"artefact_id":"art-flux","version":1,"titre":"Brouillon","type":"svg","langage":null,' +
    '"fichier_id":"fic-flux","taille_octets":10}</sortie></outil>';
  const catalogue = collecterArtefacts([], brouillon);
  verifier('brouillon — artefact collecté', catalogue.get('art-flux')?.versions.length, 1);
}

/* ---- validation : type hors liste toléré, identité manquante refusée ---- */
{
  const base = { entree: 'creer_artefact(titre : X)', termine: true, echec: false };
  const brut = {
    artefact_id: 'a',
    version: 1,
    titre: 'X',
    type: 'pdf',
    langage: null,
    fichier_id: 'f',
    taille_octets: 3,
  };
  const horsListe = versionDepuisAppel({ ...base, sortie: JSON.stringify(brut) });
  verifier('type hors liste — ramené à inconnu', horsListe?.type, 'inconnu');
  const { fichier_id: _ignore, ...sansFichier } = brut;
  verifier(
    'identité manquante — refusée',
    versionDepuisAppel({ ...base, sortie: JSON.stringify(sansFichier) }),
    null,
  );
  verifier('sortie non JSON — refusée', versionDepuisAppel({ ...base, sortie: 'Échec : disque plein' }), null);
}

/* ---- un autre outil, même complet, n'est jamais pris pour un artefact ---- */
{
  const appel = {
    entree: 'lire_fichier(chemin : x.json)',
    sortie: '{"artefact_id":"a","version":1,"titre":"X","fichier_id":"f","taille_octets":3}',
    termine: true, echec: false,
  };
  verifier('autre outil — ignoré', versionDepuisAppel(appel), null);
}

if (echecs > 0) {
  throw new Error(`${echecs} test(s) en échec.`);
}
console.log('Tous les tests de versions passent.');
