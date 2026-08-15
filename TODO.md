# TODO

## URGENT — à démarrer en premier : bac à sable et artefacts

Workflow préparé et arrêté avant exécution le 2026-08-15. Le script est prêt à relancer :
`.claude/projects/…/workflows/scripts/echohub-bac-artefacts-wf_0f08b6c0-b5a.js`

### Ce qui est demandé

- Interpréteur Python accessible aux modèles depuis la conversation, avec exécution réelle.
- Un bac à sable par conversation dans le conteneur : créer fichiers et dossiers, avec une taille
  maximale par fichier ET par bac.
- Un outil de présentation : le modèle désigne un fichier, l'utilisateur le voit.
- Au clic, ouverture en **artefact** — une modale **agrandissable**, avec dans son en-tête un
  interrupteur à **deux icônes** : code source / aperçu.
- Langages : Python (exécuté), JavaScript, TypeScript, HTML, CSS, texte brut.

### Faits MESURÉS dans le conteneur — ne pas les redécouvrir

```
python3   3.10.12        présent
bun       1.3.14         présent — seul chemin pour JS et TS
node, tsc, deno          ABSENTS
utilisateur              root (uid 0)   ← le point dangereux du sujet
cgroups v2               cpuset cpu io memory hugetlb pids rdma
unshare                  présent
nsjail, bubblewrap       absents
module python resource   fonctionne (setrlimit)
espace libre             837 Go
```

### Décisions déjà prises, à tenir

- **Abandonner root** pour l'exécution : utilisateur non privilégié créé dans le Dockerfile,
  bascule par `preexec_fn` + `setuid`. C'est la mesure qui compte le plus.
- Limites par `setrlimit` : temps CPU, mémoire adressable, taille de fichier, nombre de processus,
  descripteurs. `unshare --net` pour couper le réseau si le coût est acceptable.
- Sans namespaces de montage, l'isolation du système de fichiers a des limites RÉELLES : les
  écrire honnêtement plutôt qu'annoncer une garantie fausse.
- HTML produit par un modèle = contenu non fiable → iframe `sandbox` **sans** `allow-same-origin`,
  via `srcdoc`. La raison doit être commentée à l'endroit même de l'attribut.
- Coloration syntaxique écrite à la main, pas de dépendance lourde ajoutée au bundle.
- Un langage sans aperçu sensé (Python) : interrupteur d'aperçu **désactivé avec sa raison**, pas
  absent — sinon on croit à un bug.
- Le harnais d'outils existe déjà (`backend/outils/`) : suivre son contrat, ne pas le réécrire.
  Point à résoudre : le registre exécute un outil sans savoir de quelle conversation il vient, or
  le bac est par conversation.
- **Assemblage fait à la main après le workflow.** Le lot précédent a produit six domaines corrects
  branchés nulle part ; les périmètres cloisonnés évitent les conflits mais personne ne monte le
  résultat.

## Ensuite

- **MoE jamais chargé en conditions réelles.** Il est planifiable depuis le 2026-08-15
  (`largeur_ffn_active` sérialisée), mais aucun chargement du 35B-A3B n'a été mesuré. C'est le test
  qui dira si les 6 Go de VRAM inutilisés sont récupérés.
- **Profil machine sondé toutes les 2 secondes** par l'interface, appel NVML compris. Aucun blocage,
  mais charge permanente pour rien : 10 à 15 secondes suffiraient.
- Option de désactivation des CUDA graphs dans les réglages de chargement. Ils sont **actifs par
  défaut** (vérifié dans `libggml-cuda.so`) ; seule la désactivation est exposée par llama.cpp, et
  elle n'a d'intérêt qu'en cas de bug de capture sur Blackwell.
- GGUF en plusieurs parts : le correctif est écrit et poussé, jamais éprouvé sur un vrai
  téléchargement découpé.
- Le modèle ré-émet parfois un appel d'outil après avoir déjà reçu les résultats. Piste : retirer
  les outils du prompt au second tour, il n'a plus de raison d'en redemander.
- Le socle est en français mais les modèles répondent parfois en anglais. Imposer la langue de
  l'utilisateur.
