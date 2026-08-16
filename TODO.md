# TODO — EchoHub v2

*Dernière mise à jour : 2026-08-16*

## En cours

Rien. Session close sur un état stable, arbre git propre, application en ligne, 382 tests verts.

## À faire (priorité)

### 1. Éprouver le harnais corrigé en génération réelle

Neuf lots de correctifs sont partis aujourd'hui sans qu'aucun modèle ne soit rechargé — Chris s'en
charge lui-même. Les mécanismes sont couverts par des tests, le comportement observé ne l'est pas.

- [ ] Reprendre le scénario exact qui a échoué : « écris-moi une page HTML avec un simulateur »,
      puis « ça ne rend pas bien, corrige ». Ce que la correction doit produire :
      l'appel avec `nom` au lieu de `chemin` **écrit le fichier** ; l'erreur suivante est corrigée
      par `modifier_fichier` et non par une réécriture complète ; aucune annonce de fichier ou de
      carte qui n'existe pas.
- [ ] Vérifier que le bloc « Appel d'outil » affiche un aperçu de cinq lignes et non 12 000 caractères.
- [ ] Si un appel vide réapparaît malgré tout : le journal dit maintenant ce qui a été normalisé et
      ce qui a été refusé comme redite (`logger.info` dans `registre.executer`, `logger.warning` dans
      `_executer_appels`). Lire le journal AVANT de toucher au code.

### 2. Deux défauts moteur mesurés le 2026-08-16

- [ ] **Le verrou du moteur reste tenu après déconnexion du client** — mesuré à plus de 12 minutes.
      Une génération abandonnée côté navigateur continue d'occuper l'instance `Llama`, et tout
      comptage de contexte ou toute nouvelle génération attend derrière.
- [ ] **`/inference/decharger` pendant une génération active fait tomber le backend**, et 15,4 Go de
      VRAM ne sont pas rendus. Récupéré par `wsl --shutdown`. Le déchargement doit refuser tant
      qu'une génération tient le verrou, ou l'interrompre proprement — jamais planter.

### 3. Longueur des réponses — leviers restants

Mesuré : **rien dans l'application ne raccourcit les réponses** (quatre cellules, 6 389 à 7 904
caractères, la chaîne complète avec harnais donnant la plus longue). Les hypothèses « c'est
l'échantillonnage » puis « c'est le harnais » ont toutes deux été réfutées par la mesure.

- [ ] Aligner l'échantillonnage par défaut sur les recommandations Qwen3 (temp 0.6 / top_p 0.95 /
      top_k 20, sans pénalité de répétition) — **+14 % mesuré**, modeste mais gratuit.
- [ ] Regarder le prompt système de la conversation : c'est le levier non mesuré qui reste.
- [ ] Considérer une quantification supérieure à Q3_K_S pour le modèle utilisé.

### 4. Captures d'écran et fichiers dans les conversations

- [ ] Joindre un fichier non-image à un message (les images passent depuis le 2026-08-15)
- [ ] Transmettre au modèle chargé dès qu'il sait les lire, quel que soit le modèle

**La règle demandée, et elle est structurante** : l'application **ne bloque pas** et **n'affiche
aucun message générique** du type « ce modèle ne prend pas en charge les images ». Elle transmet. Si
le modèle chargé n'a pas de tour de vision, c'est **lui** qui répond qu'il ne voit rien, avec ses
mots. Une interface qui refuse à sa place se trompera tôt ou tard sur ce dont le modèle est capable.

### 5. Charger un MoE en conditions réelles

- [ ] Charger le 35B-A3B et mesurer : VRAM occupée, RAM, débit
- [ ] Comparer au plan calculé — le déport des experts récupère-t-il les 6 Go inutilisés ?

Planifiable depuis le 2026-08-15 (`largeur_ffn_active` sérialisée), **jamais chargé**. Tout le code
de déport existe et est couvert par des tests unitaires ; aucune mesure ne l'a validé.

### 6. Vérifications restées en suspens

- [ ] GGUF en plusieurs parts : correctif écrit et poussé, **jamais éprouvé** sur un vrai
      téléchargement découpé
- [ ] Sondage du profil machine ramené de 2 s à 10–15 s (appel NVML à chaque passage)

## Backlog

- [ ] **Compose par plateforme** : `docker-compose.windows.yml` / `docker-compose.linux.yml` choisis
      par `COMPOSE_FILE` dans le `.env` non suivi. Proposé, non tranché — en attendant, la syntaxe
      GPU fait le va-et-vient sur `main` à chaque pull, et `main` porte la forme Windows.
- [ ] **Aucune authentification** : le port 37820 est ouvert sur le LAN, et le bac exécute désormais
      du Python. À traiter avant toute exposition hors du réseau domestique.
- [ ] `_boucle_outils` fait 44 lignes au lieu des 35 de la norme. La découper imposerait de faire
      transiter trois valeurs à travers un générateur ; écart assumé, à revoir si la fonction grossit.
- [ ] Option de désactivation des CUDA graphs : livrée le 2026-08-15, jamais utilisée en pratique.
- [ ] ccremote (`../ccremote`, branche `local-models`) : l'orchestrateur exige des identifiants
      Claude. Trois voies proposées, aucune tranchée.
- [ ] Nettoyage disque : ~57 Go récupérables (image v1, volumes, venv vLLM 0.21.0 non transposable —
      ses shebangs portent des chemins absolus).

## Terminé — session du 2026-08-16

- [x] Fins de ligne forcées en LF (`.gitattributes`) — un pull Windows cassait le conteneur
- [x] Interface utilisable au téléphone : composeur, tiroirs, écran Modèles
- [x] Le harnais n'abandonne plus un appel d'outil détecté au second tour
- [x] Un tour de clôture garantit une réponse quand les trois tours ont demandé un outil
- [x] Socle et schémas d'outils en anglais ; parsing tolérant aux balises fermantes manquantes
- [x] Modale d'artefact : plus de débordement, en largeur comme en hauteur
- [x] Trois outils de fichier — écrire, lire, modifier — au lieu de tout passer par `executer_python`
- [x] Résultats d'outils en rôle `tool`, contenu nu, au lieu d'un préfixe inventé et imitable
- [x] Aperçu de cinq lignes à l'écriture, compaction à huit lignes dans l'historique renvoyé au moteur
- [x] Alias d'arguments : un synonyme ne fait plus jeter le travail du modèle
- [x] `EchecOutil` : l'échec d'un outil est porté par le type, plus deviné sur un préfixe de texte
- [x] Le balisage d'appel du modèle ne repart plus au moteur dans son propre texte
- [x] Un appel déjà échoué n'est pas rejoué à l'identique tant que rien d'autre n'a abouti
- [x] `harnais_outils.py` extrait, `_resoudre_outils` (code mort, 44 lignes) supprimé

## Terminé — sessions précédentes

- [x] L2 : exécution Python confinée, un bac à sable par conversation (2026-08-15)
- [x] L3 : artefacts dans le fil — présentation, modale agrandissable, aperçu HTML cloisonné
- [x] L5+L6 : coût en tokens d'une image mesuré via mtmd, repli sans tour de vision
- [x] L10 : outils cessés d'être repassés au moteur après un tour avec résultats ; langue imposée
- [x] Reconstruction complète de l'application (v1 abandonnée), planificateur, chat, harnais,
      panneau de contexte, écran Modèles (2026-08-14 au 2026-08-15)
