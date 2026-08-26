/*
 * Tests purs de la lecture des appels d'outils — aucune dépendance, aucun rendu, aucun navigateur.
 *
 * Lancement : `bun run frontend/src/chat/raisonnement/tests/lecture-appel.test.ts`
 * Le fichier lève à la fin s'il reste un échec : le code de sortie est non nul, exploitable en CI.
 *
 * Le harnais est volontairement recopié dans chaque dossier de tests plutôt que mutualisé :
 * mutualiser créerait un import entre modules qui n'ont aucune raison de se connaître, pour douze
 * lignes qui n'évolueront pas.
 */

import { lireAppel } from '../lecture-appel';

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

/* ---- appel terminé, outil connu : libellé, cible, état ---- */
{
  const texte = '<entree>recherche_web(requete : prix RTX 5090 France)</entree><sortie>1. LDLC — 2 199 €</sortie>';
  const appel = lireAppel(`${texte}`, false);
  verifier('outil connu — libellé', appel?.libelle, 'Recherche web');
  verifier('outil connu — cible', appel?.cible, 'prix RTX 5090 France');
  verifier('outil connu — état', appel?.etat, 'termine');
  verifier('outil connu — icône', appel?.icone, 'loupe');
}

/* ---- cible bornée à la clé suivante : l'argument long ne déborde pas sur la carte ---- */
{
  const entree = '<entree>ecrire_fichier(chemin : page.html, contenu : <!doctype html>…)</entree><sortie>ok</sortie>';
  const appel = lireAppel(entree, false);
  verifier('deux arguments — cible = premier', appel?.cible, 'page.html');
}

/* ---- alias affiché tel que reçu : la cible se lit quand même ---- */
{
  const entree = '<entree>executer_commande(cmd : gcc main.c -o main)</entree><sortie></sortie>';
  verifier('alias cmd — cible', lireAppel(entree, false)?.cible, 'gcc main.c -o main');
}

/* ---- argument multi-lignes (aperçu backend) : la cible est la première ligne ---- */
{
  const entree = '<entree>executer_python(code : import json\nprint(1)\n… (+40 lignes))</entree><sortie>';
  const appel = lireAppel(entree, true);
  verifier('multi-lignes — cible première ligne', appel?.cible, 'import json');
  verifier('sortie ouverte + génération — en cours', appel?.etat, 'en_cours');
}

/* ---- sortie ouverte SANS génération : appel coupé, pas « en cours » pour toujours ---- */
{
  const entree = '<entree>lire_fichier(chemin : notes.md)</entree><sortie>';
  verifier('sortie ouverte figée — interrompu', lireAppel(entree, false)?.etat, 'interrompu');
}

/* ---- échecs reconnus : uniquement les formes émises par le harnais lui-même ---- */
{
  const registre = "<entree>executer_commande(commande : cargo build)</entree>" +
    "<sortie>Échec de l'outil : commande introuvable : cargo</sortie>";
  verifier('échec harnais — état', lireAppel(registre, false)?.etat, 'echec');
  const inconnu = "<entree>meteo(ville : Paris)</entree><sortie>L'outil « meteo » n'existe pas.</sortie>";
  verifier('outil inconnu — état échec', lireAppel(inconnu, false)?.etat, 'echec');
  verifier('outil inconnu — libellé = nom brut', lireAppel(inconnu, false)?.libelle, 'meteo');
  const redite = '<entree>lire_fichier(chemin : x)</entree><sortie>Failed: this exact call was already made…</sortie>';
  verifier('redite — état échec', lireAppel(redite, false)?.etat, 'echec');
}

/* ---- échec libre (EchecOutil) : indiscernable d'un résultat, donc « terminé » — assumé ---- */
{
  const entree =
    '<entree>lire_fichier(chemin : absent.md)</entree><sortie>Le fichier absent.md est introuvable.</sortie>';
  verifier('échec libre — terminé (limite documentée)', lireAppel(entree, false)?.etat, 'termine');
}

/* ---- balisage illisible : null, l'appelant garde le bloc générique ---- */
{
  verifier('texte sans balises — null', lireAppel('du texte libre', false), null);
}

if (echecs > 0) {
  throw new Error(`${echecs} test(s) en échec.`);
}
console.log('Tous les tests de lecture-appel passent.');
