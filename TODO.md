# TODO — EchoHub v2

*Dernière mise à jour : 2026-08-15*

## En cours

Rien. Session close sur un état stable, arbre git propre, application en ligne.

## À faire (priorité)

### 1. URGENT — bac à sable et artefacts

Workflow préparé et **arrêté avant exécution** le 2026-08-15, à relancer tel quel :
`.claude/projects/…/workflows/scripts/echohub-bac-artefacts-wf_0f08b6c0-b5a.js`

- [ ] Interpréteur Python accessible au modèle depuis la conversation, avec exécution réelle
- [ ] Un bac à sable par conversation : fichiers et dossiers, taille max par fichier ET par bac
- [ ] Outil de présentation : le modèle désigne un fichier, l'utilisateur le voit
- [ ] Artefact au clic — modale **agrandissable**, en-tête avec interrupteur à **deux icônes**
      (code source / aperçu)
- [ ] Langages : Python (exécuté), JavaScript, TypeScript, HTML, CSS, texte brut

**Faits MESURÉS dans le conteneur — ne pas les redécouvrir :**

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

**Décisions déjà arbitrées, à tenir :**

- **Abandonner root** pour l'exécution : utilisateur non privilégié créé dans le Dockerfile,
  bascule par `preexec_fn` + `setuid`. C'est la mesure qui compte le plus.
- Limites par `setrlimit` : temps CPU, mémoire adressable, taille de fichier, nombre de processus,
  descripteurs. `unshare --net` pour couper le réseau si le coût est acceptable.
- Sans namespaces de montage, l'isolation du système de fichiers a des limites RÉELLES : les
  écrire honnêtement plutôt qu'annoncer une garantie fausse.
- HTML produit par un modèle = contenu non fiable → iframe `sandbox` **sans** `allow-same-origin`,
  via `srcdoc`. Raison commentée à l'endroit même de l'attribut.
- Coloration syntaxique écrite à la main, pas de dépendance lourde ajoutée au bundle.
- Langage sans aperçu sensé (Python) : interrupteur **désactivé avec sa raison**, pas absent —
  sinon on croit à un bug.
- Le harnais d'outils existe (`backend/outils/`) : suivre son contrat, ne pas le réécrire.
  **À résoudre** : le registre exécute un outil sans savoir de quelle conversation il vient, or le
  bac est par conversation.
- **Assemblage à la main après le workflow.** Le lot précédent avait livré six domaines corrects
  branchés nulle part : les périmètres cloisonnés évitent les conflits, mais personne ne monte le
  résultat.

### 2. Charger un MoE en conditions réelles

- [ ] Charger le 35B-A3B et mesurer : VRAM occupée, RAM, débit
- [ ] Comparer au plan calculé — le déport des experts récupère-t-il les 6 Go inutilisés ?

Il est planifiable depuis le 2026-08-15 (`largeur_ffn_active` sérialisée), mais **jamais chargé**.
Tout le code de déport existe et est couvert par des tests unitaires ; aucune mesure ne l'a validé.

### 3. Vérifications restées en suspens

- [ ] GGUF en plusieurs parts : correctif écrit et poussé, **jamais éprouvé** sur un vrai
      téléchargement découpé
- [ ] Sondage du profil machine ramené de 2 s à 10–15 s (appel NVML à chaque passage)

## Backlog

- [ ] Option de désactivation des CUDA graphs dans les réglages de chargement. Ils sont **actifs
      par défaut** (vérifié dans `libggml-cuda.so`) et seule la désactivation est exposée par
      llama.cpp : utile uniquement en cas de bug de capture sur Blackwell.
- [ ] Le modèle ré-émet parfois un appel d'outil après avoir reçu les résultats. Piste : retirer
      les outils du prompt au second tour, il n'a plus de raison d'en redemander.
- [ ] Le socle est en français mais les modèles répondent parfois en anglais. Imposer la langue.
- [ ] **Aucune authentification** : le port 37820 est ouvert sur le LAN. À traiter avant toute
      exposition hors du réseau domestique.
- [ ] ccremote (`../ccremote`, branche `local-models`) : l'orchestrateur exige des identifiants
      Claude. Trois voies proposées, aucune tranchée.
- [ ] Nettoyage disque : ~57 Go récupérables (image v1, volumes, venv vLLM 0.21.0 non
      transposable — ses shebangs portent des chemins absolus).

## Terminé — session du 2026-08-14 au 2026-08-15

- [x] Reconstruction complète de l'application (v1 abandonnée)
- [x] Planificateur de chargement, budget mémoire mesuré, dégradation conservatrice
- [x] Chat : Markdown natif, raisonnement repliable, actions au survol, branches, réglages
- [x] Harnais d'outils : socle de prompt système, recherche web SearXNG, deux dialectes d'appel
- [x] Panneau d'occupation du contexte, compté par le tokenizer du modèle chargé
- [x] Écran Modèles : filtres de capacités, favoris, inventaire du disque, menu contextuel
- [x] Clic droit sur conversations et modèles, renommage en place
- [x] MoE débloqués (`computed_field` — pydantic ne sérialise pas les `@property`)
- [x] Verrou du moteur rendu sans délai (le fil restait bloqué 30 s après déconnexion)
- [x] Routes `:path` sur registre **et** transferts (identifiants contenant un `/`)
- [x] Suppression réelle des transferts terminés ou échoués
- [x] Ordre et étiquetage corrects des blocs : étape, appel, outil, raisonnement, réponse
