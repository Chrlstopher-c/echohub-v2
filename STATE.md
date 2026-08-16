# STATE — EchoHub v2

*Dernière mise à jour : 2026-08-16*

## Résumé de l'état actuel

L'application tourne, en Docker, sur RTX 5080 16 Go / WSL2. On charge un modèle GGUF depuis un plan
calculé, on discute avec, il appelle réellement des outils, exécute du Python confiné, écrit et
édite des fichiers dans son bac, et les présente dans le fil en artefacts cliquables.

**8 domaines backend montés**, **396 tests Python verts**, typage TypeScript strict sans `any`.
Accès local et LAN sur `http://192.168.1.67:37820`. L'interface est utilisable au téléphone depuis
le 2026-08-15.

Six outils sont déclarés au modèle, dans l'ordre de la boucle de travail : `recherche_web`,
`ecrire_fichier`, `lire_fichier`, `modifier_fichier`, `executer_python`, `presenter_fichier`.

## Ce qui a été fait — session du 2026-08-16

**Le sujet de la journée : le harnais d'outils, corrigé sur transcripts réels.** Chaque correctif
part d'une conversation relue en base, jamais d'une hypothèse. Deux fois dans la session, une
hypothèse documentée mais non mesurée a été réfutée par un test contrôlé — l'échantillonnage
d'abord, les outils ensuite.

- **Fins de ligne forcées en LF** (`.gitattributes`). Un `git pull` sous Windows réécrivait
  `docker/entrypoint.sh` en CRLF et le conteneur sortait en 127 à chaque démarrage.
- **Interface mobile** : composeur, tiroirs, écran Modèles. La carte de modèle débordait de 629 px,
  cause réelle `min-width: auto` sur les enfants de grille.
- **Le harnais n'abandonne plus un appel ni la réponse.** La condition de sortie de boucle portait
  aussi sur les outils *déclarés*, devenus nuls au second tour : l'appel était détecté puis jamais
  exécuté, et le `<tool_call>` restait affiché en XML brut. Et quand les trois tours demandaient un
  outil, la conversation restait sans un mot — il y a désormais un tour de clôture.
- **Socle et schémas d'outils réécrits en anglais**, parsing des deux dialectes rendu tolérant aux
  balises fermantes manquantes.
- **Modale d'artefact** : ne déborde plus, ni en largeur ni en hauteur. Même cause que la carte de
  modèle.
- **Trois outils de fichier** (`ecrire_fichier`, `lire_fichier`, `modifier_fichier`). Avant, le seul
  moyen de produire un fichier était `executer_python` : le modèle emballait son contenu dans du
  source Python, doublement échappé, et **réécrivait tout à la moindre erreur**.
- **Les résultats d'outils repartent en rôle `tool`**, contenu nu. L'ancienne forme — rôle
  `assistant` préfixé `[outil nom — résultat]` — était un format inventé par nous, que le modèle a
  fini par imiter en prose au lieu d'appeler l'outil.
- **Aperçu des appels et compaction de l'historique.** Écrire un fichier passe son contenu entier en
  argument : le bloc affiché pesait 7 261 caractères. Cinq lignes à l'affichage, huit lignes pour
  les blocs d'outils des tours passés qui repartent au moteur.
- **Un synonyme d'argument ne fait plus jeter le travail du modèle** (voir « Contexte non-évident »).

## Décisions prises — 2026-08-16

| Décision | Raison | Date |
|---|---|---|
| Alias d'arguments déclarés par outil | Le modèle a envoyé 12 173 caractères de HTML valide avec `nom` au lieu de `chemin` : tout a été jeté. Une correspondance déclarée et testée, jamais un appariement au jugé des arguments inattendus | 2026-08-16 |
| L'échec d'un outil porté par le TYPE (`EchecOutil`) | Un outil rendait « Échec : … » avec `succes=True` ; le harnais ne pouvait pas savoir qu'un tour n'avait rien produit, et laissait annoncer un fichier inexistant. Le deviner sur le préfixe du texte cassait au premier message reformulé | 2026-08-16 |
| Le balisage d'appel du modèle ne repart pas au moteur | Un appel raté qu'on lui remontre est un gabarit qu'on lui propose : l'appel vide se rejouait à l'identique, y compris au premier tour du message suivant | 2026-08-16 |
| Anti-redite sur les ÉCHECS seulement, effacée par le premier succès | Borner toute répétition aurait cassé `lire → modifier → relire`, c'est-à-dire la boucle que ces outils existent pour permettre. Attrapé par les tests existants | 2026-08-16 |
| Résultats d'outils en rôle `tool`, contenu nu | Canal natif des gabarits (`<tool_response>`), que le modèle ne confond pas avec sa propre prose. Vérifié dans les en-têtes GGUF des 8 modèles présents | 2026-08-16 |
| Socle et schémas d'outils rédigés en anglais | Ces modèles raisonnent en anglais — visible dans chaque bloc de raisonnement — et suivent mieux une consigne de forme dans cette langue. La sortie reste en français, la première ligne du socle l'exige | 2026-08-16 |
| Écrire dans un fichier plutôt que dans `code` | Le fichier survit à l'appel : une erreur se corrige avec `modifier_fichier` au lieu de tout retaper | 2026-08-16 |
| Compaction des blocs d'outils dans le seul flux vers le moteur | Le contenu d'un outil n'a de valeur pleine que pendant le tour qui l'a demandé. L'affiché et l'enregistré restent entiers : économie de contexte, pas perte d'information | 2026-08-16 |
| `.gitattributes` avec `* text=auto eol=lf` | Sans lui, chaque checkout Windows recasse l'entrypoint du conteneur. `git add --renormalize` ne corrige que l'index | 2026-08-16 |

## Contexte non-évident

**Le harnais peut coûter plus cher que le modèle.** Mesure du 2026-08-16 : le modèle émet
`ecrire_fichier` avec le contenu entier du fichier — 12 173 caractères de HTML valide — et un
argument `nom` au lieu de `chemin`. Le harnais répond « Aucun chemin fourni » et jette tout. Le
modèle réémet alors un appel VIDE, trois tours de suite, puis annonce à l'utilisateur un fichier
inexistant et une carte qui n'est pas affichée. Un seul refus de synonyme a produit toute la
cascade. Règle qui en découle : quand l'intention d'un appel est lisible, le harnais la sert.

**Retirer ses outils au modèle après un tour l'empêchait de finir sa tâche.** Renversement du
2026-08-16, imposé par la mesure. Les outils n'étaient déclarés qu'au PREMIER tour (L10-b), pour
qu'un modèle ne redemande pas sans fin un outil dont il a déjà le résultat. Mesuré sur le MoE 35B,
contexte servi de 131 072 tokens dont 18 835 occupés — donc sans aucune contrainte de fenêtre : le
modèle appelle `lire_fichier`, apprend que le fichier n'existe pas, annonce « je repars de zéro,
voici la nouvelle version »… et s'arrête. Il n'avait pas renoncé : `ecrire_fichier` ne lui était
plus déclaré. C'est le symptôme « ça coupe alors que le contexte est large ».

La boucle que le socle DEMANDE compte plusieurs appels enchaînés — écrire, exécuter, relire,
corriger, présenter. `TOURS_OUTILS_MAX` passe donc de 3 à 6, et les outils restent déclarés à chaque
tour. Mesure avant/après sur la MÊME demande, même modèle, même conversation : 758 caractères et un
seul outil, contre **19 469 caractères et trois outils enchaînés** — le modèle écrit désormais ses
deux fichiers, les relit, et termine sa réponse. Ce que L10-b protégeait est couvert ailleurs et mieux ciblé : cette borne, l'anti-redite sur
les appels échoués, et le retrait du balisage d'appel de l'historique.

**Tout format que le harnais laisse dans le contexte finit imité.** Deux fois : le préfixe
`[outil nom — résultat]`, puis le balisage `<function=…>` d'un appel raté. Ce qui revient au modèle
comme étant son propre texte lui sert d'exemple de ce qu'il a « bien » fait.

**La fenêtre saturait, et c'était la cause.** MESURÉ le 2026-08-16 sur la conversation réelle :
48 461 tokens d'historique brut pour une fenêtre de 32 768 — un dépassement de 15 000 tokens, donc
presque aucune place pour répondre. La compaction livrée le même jour ramène ce même historique à
9 562 tokens, soit 23 000 tokens libres. C'est le correctif décisif du symptôme « ça coupe ».

**Une réponse coupée par la fenêtre est désormais reprise.** `finish_reason` existait sur le morceau
de fin de l'adaptateur et n'était lu par personne : la chaîne ne rendait que `texte`,
`tokens_generes` et `tokens_par_seconde`. Mesuré à 1 973 tokens puis `length` sur un contexte de
2 048. La reprise repart du texte déjà produit, bornée à quatre essais, et annonce la fenêtre pleine
quand elle ne peut plus rien produire. Un plafond `max_tokens` demandé par l'utilisateur, lui, est
respecté : `length` recouvre les deux causes, et le moteur ne les distingue pas.

**Les réponses courtes ne viennent pas de l'application.** Mesuré le 2026-08-16 sur quatre cellules :
6 389 à 7 904 caractères, la chaîne complète avec harnais donnant la plus longue. Rien dans le code
ne raccourcit. Les leviers restants sont le prompt système de la conversation, l'échantillonnage
Qwen3 (+14 % mesuré, non appliqué) et la quantification Q3_K_S du modèle chargé.

**La v1 était calibrée pour une autre machine.** RTX 3060, Linux natif. Nombre de couches codé en
dur, heuristique de 150 Mo par couche (436 Mo mesurés), et mémoire unifiée CUDA — inutilisable sous
WSL2, qui laisse les poids en RAM hôte avec la VRAM figée à 2 Go. Première hypothèse à tester devant
tout symptôme mémoire inexpliqué.

**`GGML_CUDA_FORCE_CUBLAS=ON` n'est pas cosmétique.** Sans lui, nvcc de CUDA 12.8 segfaute en
compilant les kernels MMQ de ggml pour `compute_120a`. Bug du compilateur. Détail dans
COMPATIBILITE-GPU.md.

**La syntaxe GPU de Docker est inversée entre plateformes.** `deploy.resources.reservations` sur
Windows/WSL2, CDI `nvidia.com/gpu=all` sur Linux natif. Les deux formes sont dans
docker-compose.yml, une seule active — **`main` porte aujourd'hui la forme Windows.**

**Le port réel est 37820, pas celui du compose.** Le défaut du compose est 37920 ; un `.env` non
suivi par git le surcharge. Lire le `.env`, pas le compose.

**Les identifiants contiennent des `/`.** `<depot>::<fichier>`, encodé `%2F` par le navigateur :
toute route les recevant a besoin de `:path`, routes suffixées déclarées **avant** la route nue.

**Pydantic ne sérialise pas les `@property`.** `computed_field` est obligatoire dès qu'une valeur
dérivée doit voyager. C'est ce qui bloquait tous les MoE.

**Aucune authentification.** Le port 37820 est ouvert sur le LAN : n'importe qui sur le réseau peut
lire les conversations, charger ou éjecter un modèle, et désormais **exécuter du Python dans le bac**.
À traiter avant toute exposition hors du réseau domestique.

**Sécurité, à ne pas perdre de vue.** Un jeton GitHub `ghp_…` collé en clair le 2026-08-14 doit être
considéré comme compromis et révoqué (https://github.com/settings/tokens). Le jeton OAuth de
`gh auth login --web` est dans le gestionnaire d'identifiants Windows de cette machine — qui n'est
pas celle de Chris. `gh auth logout` avant de la rendre.

## Prochaines étapes

Ordonnées dans TODO.md. En tête : **valider le harnais corrigé sur une vraie conversation**, puis
les deux défauts moteur mesurés (verrou retenu, plantage au déchargement).

## Points en suspens

- **Le harnais corrigé n'a pas encore été éprouvé en génération réelle.** 382 tests couvrent les
  mécanismes ; aucun modèle n'a été chargé depuis (Chris s'en charge lui-même).
- **Le MoE n'a jamais été chargé en conditions réelles.** Planifiable depuis le 2026-08-15, aucune
  mesure. C'est le test qui dira si les 6 Go de VRAM inutilisés sont récupérés.
- **Qwen3-Coder-30B en plusieurs parts** : correctif écrit, jamais éprouvé sur un vrai
  téléchargement découpé.
- **Compose par plateforme** : un découpage `docker-compose.windows.yml` / `.linux.yml` piloté par
  `COMPOSE_FILE` dans le `.env` a été proposé, non tranché. En attendant, le va-et-vient reste sur
  `main`.
- **ccremote** (`../ccremote`, branche `local-models`) : l'orchestrateur exige des identifiants
  Claude. Trois voies proposées, aucune tranchée.

## Historique

**2026-08-15 — Lots L2 à L10.** Exécution Python confinée avec un bac par conversation ; artefacts
dans le fil (présentation, modale agrandissable, aperçu HTML cloisonné) ; coût en tokens d'une image
mesuré via mtmd et repli sans tour de vision ; correction d'un plantage natif SIGABRT au premier
comptage d'image ; réglage de désactivation des CUDA graphs ; arrêt de la réémission des outils
après un tour avec résultats.

**2026-08-14 au 2026-08-15 — Reconstruction complète.** La v1 (`../echohub-master`) abandonnée après
plusieurs heures de correctifs, ses constantes étant calibrées pour une RTX 3060 sur Linux natif. La
v2 bâtie par un workflow de 15 agents, puis assemblée et corrigée à la main : planificateur de
chargement, chat complet avec branches, harnais d'outils et recherche web SearXNG, panneau
d'occupation du contexte, écran Modèles.

**2026-08-14 — Journée v1.** Lancement sous Windows, Docker Desktop et WSL2, quatre correctifs pour
démarrer. Puis diagnostic du MoE : plusieurs heures perdues à supposer un manque de VRAM avant de
tester un modèle connu-bon de 490 Mo, qui a généré immédiatement et disculpé toute la chaîne.

## Mesures de référence sur cette machine

| Modèle | Contexte | Débit |
|---|---|---|
| Qwen2.5-0.5B Q4_K_M | 32 768 | 113–120 tok/s |
| Qwen3.6-27B PHILADELPHIA Q3_K_M | 32 768 | ~72 tok/s |
| Qwen3.6-35B-A3B IQ4_XS (29/41 couches GPU) | 32 768 | 41 tok/s |
| idem | 57 344 | 19,6 tok/s |
| Huihui-Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated Q3_K_S | — | 10–20 tok/s |
