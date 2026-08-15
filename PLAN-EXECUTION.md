# PLAN-EXECUTION — EchoHub v2

*Établi le 2026-08-15. Confronte `TODO.md` au code réel, tranche les décisions d'architecture des
deux gros chantiers, et découpe le reste en lots exécutables.*

Ce document est écrit pour des équipes qui n'auront pas le contexte de celle qui l'a produit.
Tout verdict de la partie 1 est adossé à un fichier et une ligne, ou à une commande et sa sortie.
Les décisions de la partie 2 sont **prises**, pas proposées : les rediscuter coûte plus cher que
les appliquer. Ce que ce document ne dit pas sera redécidé trois fois, différemment — donc ce
qu'il dit fait foi jusqu'à ce que l'opérateur le contredise.

**État du dépôt au moment de l'audit** : branche `equipe/23297c74…` sur `2d818d6`, arbre propre.
`python -m pytest backend -q` → **196 passed in 0.93s**. `bun run typecheck` (frontend) → aucune
sortie, code 0. Machine : Arch Linux natif (noyau 7.1.3-zen), **pas WSL**, RTX 3060 12 Go, pilote
610.43.03, 38,6 Gio de RAM disponible, 78 Go libres sur `/` (476 Go, 84 % occupés).

---

## Partie 1 — Audit case par case

### 1. Bac à sable et artefacts

Verdict d'ensemble : **rien n'est commencé côté exécution**. Il n'existe aucun domaine de bac à
sable dans `backend/` (`chat`, `core`, `engines`, `inference`, `models`, `outils`, `recherche`,
`system` — rien d'autre), et aucun fichier du backend n'importe `resource` ni ne pose de
`setrlimit` : les seuls usages de `subprocess` sont `backend/engines/_processus.py`,
`backend/inference/engines_adapters/processus_vllm.py`, `adaptateur_vllm.py` et
`backend/system/nvidia_smi.py`, tous étrangers au sujet.

| Case | Verdict | Preuve |
|---|---|---|
| Interpréteur Python accessible au modèle, exécution réelle | **pas commencé** | `backend/outils/registre.py:25` — le registre ne contient qu'un outil, `OUTIL_RECHERCHE`. Aucun autre n'est enregistré nulle part. |
| Un bac par conversation, taille max par fichier et par bac | **pas commencé** | Aucun domaine de fichiers ; `backend/core/config.py:33` ne dérive que `models_dir` et `engines_dir` sous `data_home`. |
| Outil de présentation (le modèle désigne, l'utilisateur voit) | **pas commencé** | Même preuve : un seul outil déclaré, `registre.py:25`. |
| Artefact au clic — modale agrandissable, interrupteur deux icônes | **pas commencé, socle partiel** | `frontend/src/shared/design/Modal.tsx:21-25` : tailles `sm/md/lg` figées, aucun mode agrandi ; aucun composant d'artefact dans `frontend/src/chat/`. |
| Langages : Python exécuté, JS, TS, HTML, CSS, texte | **partiellement fait (rendu seulement)** | `frontend/src/chat/markdown/coloration.ts:33-38` : familles `ts/tsx/js/jsx/json`, `py`, `sh`, `rs`. **HTML et CSS ne sont pas couverts.** `BlocCode.tsx` (54 lignes) rend déjà un bloc avec en-tête, langage et bouton copier — l'interrupteur code/aperçu s'y greffe. |

**L'arbitrage « coloration écrite à la main » est déjà tenu** : `coloration.ts` fait 101 lignes,
sans dépendance. Le lot artefacts l'étend (HTML, CSS), il ne le remplace pas.

**Le problème signalé sur le harnais d'outils est RÉEL.** Contrat exact, tel qu'il est aujourd'hui :

- un outil est `Outil{description: DescriptionOutil, executer: Execution}` —
  `backend/outils/contrat.py:71-81` ;
- `Execution = Callable[[dict[str, Any]], Awaitable[str]]` — `contrat.py:68`. **La signature
  n'admet qu'un dictionnaire d'arguments : aucun canal pour une identité de conversation** ;
- l'exécution passe par `async def executer(nom: str, arguments_bruts: object) -> ResultatOutil`
  — `backend/outils/registre.py:59`. Deux paramètres, aucun n'est un contexte ;
- l'appelant est `backend/inference/__init__.py:160` et `:190` (`from backend.outils import
  executer`), dans `MoteurChat._flux`.

La rupture se situe **avant**, et précisément ici : `backend/chat/port_inference.py:44-55`,
`RequeteGeneration{messages, parametres, modele_id}` — **le champ `conversation_id` n'existe pas**.
Il est pourtant disponible à l'endroit exact où la requête est construite :
`backend/chat/generation.py:241` crée `RequeteGeneration(...)` et la ligne **243** passe
`conversation_id=conversation_id` à `PreparationGeneration`. L'identité est donc perdue
volontairement à la frontière, deux lignes avant d'être réutilisée à côté. Côté route, elle
existe encore : `backend/chat/routes.py:176` (`generer(conversation_id, corps)`).

Chaîne complète à réparer, dans l'ordre :
`routes.py:176` → `generation.py:241` → `port_inference.py:44` → `inference/__init__.py:235`
(`MoteurChat._flux`) → `registre.py:59` → `contrat.py:68`.

### 2. Captures d'écran et fichiers dans les conversations

| Case | Verdict | Preuve |
|---|---|---|
| Joindre une image (collée, glissée, choisie) | **pas commencé** | `frontend/src/chat/conversation/Composeur.tsx` (123 lignes) : `textarea` seul, aucun `onPaste`, `onDrop` ni `input[type=file]`. |
| Joindre un fichier | **pas commencé** | Aucune route d'envoi de fichier : `backend/chat/routes.py` ne déclare que conversations, réglages, messages, branche, arbre, générer/rejouer/éditer, annuler. |
| Transmettre au modèle dès qu'il sait les lire | **pas commencé** | `backend/inference/engines_adapters/adaptateur_llama_cpp.py:269-290` (`_parametres`) : `model_path`, `n_ctx`, `n_batch`, `n_gpu_layers`, `verbose`, éventuellement `flash_attn`, `type_k/type_v`. **Aucun `chat_handler`, aucun `mmproj`.** |

**Ce que le TODO annonce comme existant est vrai** : `backend/models/storage.py:148-160`
(`fichiers_projecteurs`, filtre `mmproj*.gguf`) et `backend/models/capacites.py:38, 111, 174`
(capacité `VISION` avec ses règles de déduction).

**`MessageChat.content` est bien un `str` aujourd'hui** —
`backend/inference/engines_adapters/contrat.py:113-119`. Mais il y a **trois** représentations de
message dans la chaîne, et il faut les nommer pour ne pas les confondre :

1. `backend/chat/modeles.py:83-103` — `MessageChat` **persisté**, champ `contenu: str` (ligne 96) ;
2. `backend/chat/port_inference.py:35-41` — `MessageInference`, champ `contenu: str`, `extra="forbid"` ;
3. `backend/inference/engines_adapters/contrat.py:113-119` — `MessageChat` **moteur**, champ
   `content: str`, c'est celui qui part au moteur.

Points de la chaîne que rendre ce champ multimodal viendrait toucher — **liste complète** :

- `contrat.py:119` — le type du champ lui-même ;
- `contrat.py:309-326` (`decouper_segments`) — lit `message.content` comme un texte aux lignes
  315, 319, 321, et le passe à `separer_raisonnement` (`:274`) ;
- `contrat.py:179-198` — `PosteContexte` : un contenu d'image n'entre dans aucun poste existant ;
- `backend/inference/api.py:123` — borne de garde `sum(len(message.content) …)`, casse sur une liste ;
- `backend/inference/__init__.py:69-80` (`_messages_depuis`) — reconstruit `MessageChat(role, content)`
  depuis les objets du port, et `:170`, `:212`, `:258` fabriquent des messages assistant en texte ;
- `adaptateur_llama_cpp.py:415` et `:487` — `messages=[message.model_dump() for message in messages]`,
  **le point d'entrée naturel du multimodal** : ce que `model_dump` produit est exactement ce que
  `create_chat_completion` reçoit ;
- `adaptateur_llama_cpp.py:590-608` (`_compter_un`) — tokenise `texte.encode("utf-8")` ;
- `backend/inference/engines_adapters/adaptateur_vllm.py` — second consommateur du même contrat ;
- `backend/chat/port_inference.py:35-41` — `MessageInference` (et son `extra="forbid"`) ;
- `backend/chat/depot.py:113` — `INSERT INTO messages (…, contenu, …)`, et
  `_MIGRATIONS_CHAT` (`depot.py:85`) pour toute évolution de schéma ;
- `backend/chat/modeles.py:96, 197, 218` — `contenu: str` persisté et corps de requêtes ;
- frontend : `frontend/src/shared/api/types-chat.ts`, `chat/conversation/Message.tsx`,
  `FilMessages.tsx`, `Composeur.tsx`, `chat/contexte/postes.ts` (miroir des postes de contexte).

### 3. Charger un MoE en conditions réelles

| Case | Verdict | Preuve |
|---|---|---|
| Charger le 35B-A3B et mesurer VRAM/RAM/débit | **pas commencé** | Aucun relevé nulle part dans le dépôt ; le stack n'est pas lancé (aucun conteneur `echohub` dans `docker ps`, aucun port 3792x en écoute). |
| Comparer au plan calculé (le déport récupère-t-il 6 Go ?) | **pas commencé** | Idem — dépend de la case précédente. |

**L'affirmation « tout le code de déport existe et est couvert par des tests unitaires » est
VRAIE.** Le code : `backend/inference/engines_adapters/experts_hote.py`, 294 lignes —
`verifier_support` (`:102`, contrôle de l'ABI avant tout écrit dans la struct C), `motif_experts`
(`:169`, regex ciblant les trois tenseurs `ffn_*_exps` d'un bloc), la table de surcharges
(`:180-201`), le `CollecteurJournal` (`:203-243`, capte le journal de llama.cpp pour **vérifier**
le déport au lieu de le supposer) et le contexte `deport_actif` (`:246`). Il est branché :
`adaptateur_llama_cpp.py:128` (`_instancier_avec_deport`), `:153` (`_noter_deport`), `:167`
(`_echec_deport`), avec la cause `DEPORT_EXPERTS_INDISPONIBLE` déclarée à `contrat.py:47`.

Les tests : **11** dans `tests/test_deport_experts.py` (lignes 44, 52, 59, 66, 77, 94, 106, 116,
124, 139, 154), **12** dans `backend/models/tests/test_mesures_experts.py`, **14** dans
`backend/inference/planner/tests/test_moe.py`. Ils couvrent : le motif regex ne déborde pas sur le
bloc voisin ni sur d'autres tenseurs, la struct de surcharge n'est pas celle de quantification, le
tableau se termine par une entrée nulle, un binding dont la disposition a changé est refusé, **un
déport non confirmé par le journal vaut échec** (et un journal muet aussi), le plan transporte bien
les blocs déportés, la cause d'échec disqualifie la stratégie.

Ce qu'ils **ne** couvrent pas, et c'est tout l'objet du lot de mesure : aucun ne charge de modèle.
`llama_cpp` n'est même pas installé dans le venv natif — les 196 tests passent en 0,93 s, ce qui
serait impossible avec un chargement réel. Les tests prouvent que le mécanisme est correct ; ils ne
prouvent rien sur ce qu'il rend en VRAM.

**Le modèle 35B-A3B est présent sur le disque de cette machine — mais invisible pour la v2.**

- `/mnt/models/echohub/unsloth--Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` —
  22 134 528 992 octets (**20,6 Gio**) ;
- `/mnt/models/lmstudio-community/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-Q4_K_M.gguf` —
  21 166 757 728 octets (**19,7 Gio**) ;
- et son projecteur : `/mnt/models/lmstudio-community/Qwen3.6-35B-A3B-GGUF/mmproj-Qwen3.6-35B-A3B-BF16.gguf`
  — 902 822 016 octets (861 Mio). **Ce MoE est aussi un modèle de vision** : le même chargement
  peut servir les deux chantiers.

Mais `docker volume inspect echohub_echohub_models` → `/var/lib/docker/volumes/echohub_echohub_models/_data`,
et `du -sh` sur ce chemin rend **0**. Le volume est **vide**. Or `docker-compose.yml:52` et `:64`
montent `echohub_models:/data/models` avec `MODELS_DIR: /data/models`, et il n'y a **pas de
`.env`** dans le projet pour redéfinir quoi que ce soit. `/mnt/models` est l'arborescence de la
v1 : la v2 ne la voit pas.

**Conséquence pour la planification : la mesure du 35B-A3B est planifiable, mais elle exige une
décision d'accès aux fichiers** (bind mount en lecture seule, ou copie de ~20 Go dans le volume —
78 Go libres, ça tient, mais ça consomme). Voir lot **L7**, marqué décision opérateur.

Autres modèles présents, utiles aux lots vision : `Qwen3-VL-2B-Instruct` (plusieurs quantifications,
de 968 Mio à 1,7 Gio) dans `/mnt/models/echohub/unsloth--Qwen3-VL-2B-Instruct-GGUF/`,
`Qwen3-VL-8B-Instruct-Q4_K_M.gguf` (4,7 Gio) + `mmproj-Qwen3-VL-8B-Instruct-F16.gguf` (1,08 Gio),
`gemma-4-E4B-it` + son mmproj (947 Mio).

### 4. Vérifications restées en suspens

| Case | Verdict | Preuve |
|---|---|---|
| GGUF en plusieurs parts | **correctif présent, ZÉRO test, jamais éprouvé** | Le code existe : `backend/models/download_selection.py:27-41` (`parts_du_meme_modele`, convention `<base>-00001-of-00003.gguf`) et `:84-86` (le total couvre toutes les parts), `download.py:138-141`, `download_worker.py:31-43`. Mais `backend/models/tests/` ne contient que `test_capacites`, `test_coherence_moe`, `test_gguf_moe`, `test_mesures_experts` : **aucun test ne mentionne `of-0` ni `00001`**. L'affirmation « correctif écrit et poussé » est vraie ; « jamais éprouvé » l'est aussi, et il n'y a même pas de couverture unitaire. Un modèle en deux parts est présent sur disque (`/mnt/models/echohub/Qwen--Qwen2.5-Coder-14B-Instruct-GGUF/…-00001-of-00002.gguf`) : la convention est bien celle attendue. |
| Sondage du profil machine « ramené de 2 s à 10–15 s » | **pas commencé — et la formulation du TODO induit en erreur** | La constante est inchangée : `frontend/src/system/materiel/useProfilMachine.ts:18` → `INTERVALLE_PROFIL_MS = 2000`. |

**Mesure chronométrée du sondage — le point est tranché.** Commande exécutée avec le venv du
projet (`backend/.venv/bin/python`), sur cette machine :

```
import=0.372s   appel1=0.029s   appel2=0.016s   source=SourceMesureGpu.NVML
```

`profil_machine()` coûte **29 ms au premier appel, 16 ms ensuite** — pas 10 s, pas 1 s. **Le
« 10–15 s » du TODO n'est pas une latence observée : c'est la nouvelle CADENCE de sondage
souhaitée** (passer l'intervalle de rafraîchissement de 2 s à 10–15 s parce que chaque passage
refait un cycle NVML complet). Toute équipe qui partirait chercher une latence de 10 s dans
`backend/system/` perdrait sa journée : il n'y en a pas.

La cause du coût, elle, est réelle et identifiée : `backend/system/nvml.py:111-133` fait
`nvmlInit()` à chaque appel (`:122`) et `nvmlShutdown()` dans le `finally` (`:132`, via `_fermer`)
— la session NVML ne survit jamais à la mesure, par choix documenté (aucune valeur ne peut être
servie depuis un état gardé en mémoire). À 2 s d'intervalle, cela fait 30 cycles init/shutdown par
minute et par onglet ouvert.

**Réserve d'honnêteté** : cette mesure a été prise en natif, hors conteneur. Dans l'image
`echohub:gpu`, NVML traverse le runtime NVIDIA du conteneur et le coût peut être supérieur —
il n'a **pas** été mesuré, le stack n'étant pas lancé. Le lot L9 le mesure avant de choisir la
valeur exacte entre 10 et 15 s.

### Backlog

| Case | Verdict | Preuve |
|---|---|---|
| Désactivation des CUDA graphs dans les réglages | **pas commencé** | `grep -rn "GGML_CUDA_DISABLE_GRAPHS\|cuda_graph"` sur `backend/` et `frontend/src/` → **aucune occurrence**. Le plan sait déjà transporter des variables d'environnement (`contrat.py:95`, `variables_env`) et l'adaptateur les applique (`adaptateur_llama_cpp.py:249`) : le branchement est court. |
| Ré-émission d'un appel d'outil après réception des résultats | **pas commencé, cause confirmée** | `backend/inference/__init__.py:235` calcule `outils = format_moteur()` **une fois, hors boucle**, et `:243` le repasse à `superviseur.generer` **à chaque tour** de la boucle `for tour in range(TOURS_OUTILS_MAX)` (`:241`, `TOURS_OUTILS_MAX = 3` à `:87` ; même schéma dans `_resoudre_outils`, `:198`). Les outils restent donc déclarés au second tour : la piste du TODO (les retirer une fois les résultats reçus) porte exactement sur ces deux lignes. |
| Modèles qui répondent en anglais | **pas commencé** | Aucune mention de langue dans `backend/outils/socle.py` ni dans `backend/chat/generation.py`. Le socle énonce des faits sur l'environnement (`socle.py:28-55`), rien sur la langue de réponse. |
| Aucune authentification, port 37920 ouvert sur le LAN | **confirmé, pas commencé** | `backend/main.py` : aucun `Depends` d'authentification, aucun middleware d'auth ; seul garde-fou, un CORS `allow_origin_regex=r"^https?://(localhost\|127\.0\.0\.1)(:\d+)?$"` (`main.py:107`) — **qui ne protège rien** : le CORS est une politique de navigateur, un `curl` depuis n'importe quelle machine du LAN l'ignore. `docker-compose.yml:46-47` publie `37920:80` et `37921:37921` sur toutes les interfaces. |
| ccremote, branche `local-models` | **hors périmètre de ce dépôt** | Rien à auditer ici : `../ccremote` n'appartient pas à ce projet. Reste une question ouverte pour l'opérateur. |
| Nettoyage disque ~57 Go | **chiffre non reproductible en l'état** | Mesuré : image `echohub:gpu` **17,2 Go**, `nvidia/cuda:12.8.0-devel-ubuntu22.04` **14,6 Go**, `nvidia/cuda:12.8.0-base` 400 Mo. Les volumes `echohub_echohub_models` et `echohub_echohub_userdata` sont à **0**. `df` : **78 Go libres sur 476**. Le TODO mentionne par ailleurs « espace libre 837 Go » dans ses faits mesurés en conteneur : cette valeur ne correspond à rien sur cette machine aujourd'hui — ne pas s'en servir pour dimensionner quoi que ce soit. |

### Remarque transverse sur les tests frontend

`bun test` rend `Ran 0 tests across 2 files` et **sort 0** : `parseur.test.ts` et
`extraction.test.ts` sont des scripts qui lèvent (`parseur.test.ts:147`) au lieu d'utiliser l'API
de test de Bun. Ils sont valides — `bun run src/chat/markdown/tests/parseur.test.ts` sort 0 quand
tout passe et lèverait sinon — mais **aucun lot ne doit prendre `bun test` comme critère de
vérification** : il serait vert quoi qu'il arrive. Utiliser `bun run <fichier>.test.ts`.

---

## Partie 2 — Décisions d'architecture

Les arbitrages venus de l'opérateur (utilisateur non privilégié plutôt que root, `setrlimit`,
iframe `sandbox` sans `allow-same-origin` via `srcdoc`, coloration sans dépendance lourde,
interrupteur désactivé-avec-raison plutôt qu'absent, honnêteté sur les limites réelles de
l'isolation sans namespaces de montage) sont **appliqués tels quels**. Ce qui suit les complète là
où le TODO laissait le choix ouvert.

### 2.1 — Un seul magasin de fichiers, commun aux deux chantiers

**Décision.** Un domaine unique `backend/fichiers/` porte tout ce qui est fichier de conversation,
qu'il vienne de l'utilisateur ou du modèle. **Il n'existe pas deux mécanismes.** Un fichier joint
et un fichier produit ne se distinguent que par une colonne `origine`.

Disposition sur le disque, dérivée de `settings.data_home` comme tout le reste
(`backend/core/config.py:33` en donne le motif, aucun chemin absolu n'est écrit en dur) :

```
<data_home>/echohub-v2/conversations/<conversation_id>/fichiers/<id_fichier>.<ext>   ← le magasin
<data_home>/echohub-v2/conversations/<conversation_id>/bac/                          ← le bac à sable
```

Le **bac est le répertoire de travail du processus Python confiné**, et rien d'autre. Après chaque
exécution, le backend compare le contenu du bac avant et après, et **enregistre les nouveaux
fichiers dans le magasin** avec `origine='modele'`. C'est ce balayage qui fait que les deux
chantiers partagent réellement un seul mécanisme : le modèle n'a aucune API d'enregistrement à
appeler, il écrit des fichiers, point.

Table SQLite (migration **additive** ajoutée à `_MIGRATIONS_CHAT`, `backend/chat/depot.py:85` —
aucune ligne existante réécrite) :

```
fichiers_conversation(
  id TEXT PK, conversation_id TEXT NOT NULL, message_id TEXT NULL,
  origine TEXT NOT NULL CHECK (origine IN ('utilisateur','modele')),
  nom_affiche TEXT NOT NULL, chemin_relatif TEXT NOT NULL,
  type_mime TEXT NOT NULL, taille_octets INTEGER NOT NULL,
  empreinte_sha256 TEXT NOT NULL, cree_le TEXT NOT NULL)
```

Règles non négociables :

- **les octets ne vivent jamais en base.** La table porte des références ; le contenu vit sur le
  disque. Une image en base64 dans `messages.contenu` ferait exploser le coût de toute lecture de
  conversation, y compris celles qui n'affichent pas l'image ;
- **le type MIME est validé, jamais deviné depuis l'extension du nom fourni.** Le nom vient de
  l'utilisateur ou du modèle : c'est une entrée non fiable. Le nom d'origine est conservé pour
  l'affichage (`nom_affiche`), le nom sur disque est l'identifiant ;
- **deux quotas, tous deux vérifiés côté backend avant écriture** : taille maximale par fichier et
  taille maximale cumulée par bac. Le `setrlimit` du processus confiné (`RLIMIT_FSIZE`) est un
  second filet, pas le premier — un processus tué par sa rlimit ne dit rien d'utilisable à
  l'utilisateur ;
- **la suppression d'une conversation supprime son dossier.** `backend/chat/depot.py:244`
  (`supprimer_conversation`) doit appeler le magasin. Sans cela le disque fuit silencieusement ;
- service par une route unique `GET /api/fichiers/{id}`, avec `Content-Disposition` et le type MIME
  enregistré. C'est la même route pour un artefact produit et pour une pièce jointe.

### 2.2 — Contrat de message multimodal

**Décision, niveau par niveau** (les trois représentations identifiées en partie 1) :

1. **Persistance (`backend/chat/modeles.py:96`) : `contenu: str` reste inchangé.** Les pièces
   jointes d'un message sont une **relation** (`fichiers_conversation.message_id`), pas un champ.
   Cela évite toute migration destructive et garde lisible la table `messages`.
2. **Port `chat` → `inference` (`port_inference.py:35-41`) : `MessageInference` gagne
   `pieces: list[PieceJointe]`** où `PieceJointe{chemin: Path, type_mime: str, nom_affiche: str}`.
   **Des chemins, jamais des octets, jamais du base64 sur ce chemin** — le port est traversé à
   chaque tour de génération, y transporter des mégaoctets encodés serait payé à chaque fois.
3. **Contrat moteur (`contrat.py:119`) : `content: str | list[PartieContenu]`**, avec
   `PartieContenu` = `{"type": "text", "text": str}` ou
   `{"type": "image_url", "image_url": {"url": "data:<mime>;base64,…"}}`.
   Cette forme n'est pas un choix esthétique : **c'est exactement ce que `llama-cpp-python` lit**
   (`llama_chat_format.py:3146-3156` et `:3673-3690`, `get_image_urls`). L'union garde `str`
   valide, donc l'existant et les 196 tests continuent de passer sans réécriture.
4. **L'encodage en data URI se fait au dernier moment, dans l'adaptateur**, juste avant
   `create_chat_completion` (`adaptateur_llama_cpp.py:415` et `:487`, qui font déjà
   `message.model_dump()`). Le base64 ne traverse ni la base, ni le port, ni le domaine `chat`.
5. **Une fonction unique `texte_de(message) -> str`** dans `contrat.py`, utilisée par
   `decouper_segments` (`:315, :319, :321`) et par `backend/inference/api.py:123` : elle concatène
   les parties `text` et ignore les parties image. Aucun autre endroit ne doit inspecter `content`
   à la main — sinon la prochaine forme de contenu cassera cinq fichiers au lieu d'un.

**Côté moteur llama.cpp — ce que la version installée expose RÉELLEMENT.** Vérifié dans le paquet
de l'image `echohub:gpu`, pas dans la documentation
(`/app/backend/.venv/lib/python3.10/site-packages/llama_cpp/`, `llama_cpp_python-0.3.34.dist-info`) :

- **`MTMDChatHandler`** — `llama_chat_format.py:3269`. C'est le gestionnaire moderne, adossé à
  `libmtmd.so` (présente, 1 252 240 octets dans `llama_cpp/lib/`) via le binding `mtmd_cpp.py`
  (32 675 octets). Il prend le **projecteur en argument de construction** (`clip_model_path`,
  `llama_chat_format.py:2776`, vérifié existant à `:2785`), initialise le contexte mtmd
  (`mtmd_init_from_file`, `:2809`) et **refuse si le projecteur n'apporte pas la vision**
  (`mtmd_support_vision`, `:2819`) ;
- l'ancienne famille est là aussi : `Llava15ChatHandler` (`:2736`), `Llava16ChatHandler` (`:3876`),
  `MiniCPMv26ChatHandler` (`:4032`), `Qwen25VLChatHandler` (`:4069`), `Gemma4ChatHandler` (`:3774`,
  qui hérite de `MTMDChatHandler`), `NanoLlavaChatHandler`, `MoondreamChatHandler`,
  `Llama3VisionAlphaChatHandler` ;
- le flux réel : le handler rend le gabarit Jinja du modèle en y insérant un **marqueur média**
  (`mtmd_default_marker`, `mtmd_cpp.py:238`), charge chaque image en bitmap, puis appelle
  **`mtmd_tokenize`** (`mtmd_cpp.py:474`) qui produit une liste de *chunks* — texte et image
  mélangés — évalués ensuite dans le contexte.

**Décision de chargement** : le projecteur est choisi par `storage.fichiers_projecteurs()`
(`backend/models/storage.py:148`) dans le dossier du modèle, et passé à `MTMDChatHandler` ;
`Llama(**parametres)` reçoit alors `chat_handler=`. `_parametres` (`adaptateur_llama_cpp.py:261`)
est le seul endroit qui change. **Un mmproj absent n'empêche jamais le chargement du modèle** : on
charge sans handler et on continue (voir 2.4).

### 2.3 — Le coût en tokens d'une image est MESURÉ, jamais estimé

**Décision.** `mtmd_cpp.py` expose `mtmd_input_chunk_get_n_tokens(chunk)` (**ligne 486**) et
`mtmd_input_chunks_size` / `mtmd_input_chunks_get`. La mesure est donc directement disponible :

1. construire l'entrée comme le fait le handler (`mtmd_input_text` + bitmaps) ;
2. appeler `mtmd_tokenize` (`mtmd_cpp.py:474`) ;
3. **sommer `mtmd_input_chunk_get_n_tokens` sur les chunks**. C'est le nombre exact de tokens que
   l'image occupera dans la fenêtre, produit par le même code qui l'y placera.

Cela devient `AdaptateurMoteur.compter_multimodal(...)`, à côté de `compter_tokens`
(`adaptateur_llama_cpp.py:316`), et rend le même `ComptageTokens` (`contrat.py:259-271`). **Sans
projecteur chargé, `possible=False` avec sa raison** — exactement la discipline déjà en place
(`contrat.py:262-264` : « une mesure absente se déclare absente, elle ne se dégrade pas en zéro »).

Un poste `PosteContexte.IMAGES` est ajouté (`contrat.py:179-198` et son miroir
`frontend/src/chat/contexte/postes.ts`), alimenté par cette mesure seule.

**Formellement interdit** : toute formule du type « nombre de patchs = (largeur/14) × (hauteur/14) »,
tout facteur multiplicatif, toute constante par modèle. La v1 est morte de « 4 caractères = 1 token »
(`contrat.py:174-176`) ; ce projet ne réintroduit pas la même faute sous une autre unité.

### 2.4 — La règle des pièces jointes : l'application transmet, elle ne juge pas

**Règle structurante de l'opérateur, rappelée ici parce qu'elle sera tentante à violer :
l'application ne bloque jamais et n'affiche jamais de message générique du type « ce modèle ne
prend pas en charge les images ». Elle transmet. Si le modèle chargé n'a pas de tour de vision,
c'est LUI qui répond qu'il ne voit rien, avec ses mots.** Une interface qui refuse à sa place se
trompera tôt ou tard sur ce dont le modèle est capable, et retirera à l'utilisateur une réponse qui
aurait pu venir.

Conséquences opérationnelles, à respecter à la lettre :

- la capacité `VISION` (`capacites.py:38`) et `fichiers_projecteurs()` (`storage.py:148`) servent à
  **choisir le projecteur à charger**. Elles ne servent **jamais** à autoriser, refuser, griser un
  bouton ou afficher un avertissement ;
- le composeur accepte l'image quel que soit le modèle chargé, y compris si aucun n'est chargé ;
- **seul repli autorisé**, dans l'adaptateur et nulle part ailleurs : si le moteur chargé n'a pas de
  handler multimodal, les parties image sont remplacées, **dans le message utilisateur lui-même**,
  par une ligne factuelle du type `[image jointe : capture.png, 1024×768, 214 Ko]`. C'est une
  **donnée** transmise au modèle, pas un refus adressé à l'utilisateur : le modèle sait qu'une image
  existe, il répond ce qu'il veut. Le repli est journalisé (`logger.info`), et l'interface, elle,
  ne dit rien.

### 2.5 — Comment l'identité de la conversation atteint l'exécution d'un outil

**Décision, en quatre modifications et pas une de plus :**

1. `RequeteGeneration` (`port_inference.py:44-55`) gagne `conversation_id: str` **obligatoire**.
   La valeur est déjà sous la main à `generation.py:241` (elle est passée ligne 243) ;
2. un `ContexteExecution` **immuable** (`frozen`) est défini dans `backend/outils/contrat.py` :
   `{conversation_id: str, racine_bac: Path}` ;
3. `Execution` (`contrat.py:68`) devient
   `Callable[[dict[str, Any], ContexteExecution], Awaitable[str]]`, et `registre.executer`
   (`registre.py:59`) prend un troisième paramètre `contexte`. `recherche_web` l'ignore ;
4. `MoteurChat._flux` (`inference/__init__.py:231-243`) construit le contexte depuis la requête et
   le transmet à `_executer_appels` / `_resoudre_outils` (`:157`, `:173`).

**Pourquoi un objet et pas l'identifiant nu** : le bac a besoin du chemin résolu, et l'outil de
présentation aura besoin du magasin. Passer un `str` obligerait chaque outil à reconstruire le
chemin, donc à dupliquer la politique de nommage — et la première divergence entre deux
reconstructions serait un fichier écrit dans le bac d'une autre conversation.

**Formellement interdit** : une variable globale, un `contextvars` implicite, un attribut posé sur
le module `registre`. Le registre **reçoit** l'identité en paramètre. Le fait qu'une seule
génération puisse tourner à la fois aujourd'hui (verrou de `adaptateur_llama_cpp.py`) est une
propriété du moteur, pas une garantie d'architecture : elle ne doit jamais devenir un postulat.

### 2.6 — Bac à sable : ce qui est décidé, et ce qu'on avoue ne pas garantir

- **Utilisateur non privilégié créé dans le `Dockerfile`** (uid fixe, sans shell, sans home
  utilisable), bascule par `preexec_fn` : **d'abord les `setrlimit`, puis `setgid`, puis `setuid`**
  — dans cet ordre, `setuid` étant irréversible ;
- limites posées : `RLIMIT_CPU` (temps processeur), `RLIMIT_AS` (mémoire adressable),
  `RLIMIT_FSIZE` (taille de fichier), `RLIMIT_NPROC` (processus), `RLIMIT_NOFILE` (descripteurs).
  Le module `resource` fonctionne dans le conteneur (fait déjà relevé au TODO) ;
- `unshare --net` pour couper le réseau si le coût de démarrage reste acceptable ; **si la mesure
  montre que ce n'est pas tenable, on ne coupe pas le réseau et on l'écrit** dans l'interface, au
  lieu d'annoncer une garantie fausse ;
- **limite réelle, à écrire noir sur blanc dans l'interface** (pas dans un commentaire de code que
  l'utilisateur ne lira jamais) : sans namespaces de montage (`nsjail` et `bubblewrap` sont absents
  du conteneur), **le processus voit le système de fichiers du conteneur en lecture**. Ce qui est
  garanti : il écrit dans le bac de sa conversation, il n'est pas root, il est borné en CPU, en
  mémoire, en taille de fichier et en nombre de processus. Ce qui n'est pas garanti : qu'il ne
  puisse rien lire ailleurs dans le conteneur ;
- **HTML produit par un modèle = contenu non fiable** → aperçu dans une `iframe` `sandbox`
  **sans `allow-same-origin`**, alimentée par `srcdoc`, avec la raison commentée à l'endroit exact
  de l'attribut ;
- **interrupteur code/aperçu à deux icônes**, et pour un langage sans aperçu sensé (Python, texte
  brut) : **désactivé avec sa raison au survol**, jamais absent — un contrôle manquant se lit comme
  un bug.

### 2.7 — Règle d'assemblage (leçon du lot précédent)

Le lot précédent « avait livré six domaines corrects branchés nulle part ». **Aucun lot de ce plan
n'est terminé tant que son livrable n'est pas atteignable depuis l'interface ou depuis une commande
que son équipe exécute elle-même.** Un domaine complet, testé et non appelé compte comme *non
livré*. Chaque critère de vérification ci-dessous est écrit pour rendre cette triche impossible.

---

## Partie 3 — Lots

Ordre de lecture : les lots sont numérotés dans l'ordre d'exécution. Les deux chantiers partagent
**L0** ; ils divergent ensuite (L1→L3 pour le bac, L4→L6 pour le multimodal) et peuvent être menés
par deux équipes en parallèle **une fois L0 fusionné**, jamais avant.

### L0 — Magasin de fichiers de conversation

- **Produit** : domaine `backend/fichiers/` (modèle Pydantic, dépôt SQLite, quotas, calcul
  d'empreinte), migration additive dans `_MIGRATIONS_CHAT` (`depot.py:85`), routes
  `POST /api/conversations/{id}/fichiers` et `GET /api/fichiers/{id}`, suppression du dossier
  branchée dans `depot.supprimer_conversation` (`depot.py:244`).
- **Précondition** : aucune.
- **Vérification** : `python -m pytest backend -q` vert (196 + nouveaux) ; puis, backend lancé,
  `curl -F` d'un fichier suivi d'un `GET` qui rend **le même sha256** ; suppression de la
  conversation → le dossier n'existe plus sur le disque (`test -d` échoue).

### L1 — L'identité de la conversation atteint l'outil

- **Produit** : `conversation_id` dans `RequeteGeneration` (`port_inference.py:44`), rempli à
  `generation.py:241` ; `ContexteExecution` dans `backend/outils/contrat.py` ; nouvelle signature
  d'`Execution` (`contrat.py:68`) et de `registre.executer` (`registre.py:59`) ; transmission dans
  `inference/__init__.py:157-243`.
- **Précondition** : L0 fusionné (le contexte porte la racine du bac).
- **Vérification** : un test unitaire enregistre un outil factice, déclenche une génération avec un
  faux moteur, et **assert que l'outil a reçu l'identifiant de la conversation attendue** ;
  `pytest backend -q` vert. Le test doit être validé dans les deux sens : retirer le champ de la
  requête doit le faire échouer.

### L2 — Exécution Python confinée

- **Produit** : outil `executer_python` enregistré dans `registre.py:25` ; `Dockerfile` créant
  l'utilisateur non privilégié ; lanceur avec `preexec_fn` (rlimits → setgid → setuid) ;
  balayage du bac après exécution alimentant le magasin de L0 ; texte des limites réelles destiné à
  l'interface.
- **Précondition** : L1 fusionné ; image reconstruite (`docker compose build`).
- **Vérification**, dans le conteneur, par un script qui sort 0 et qui affiche ce qu'il a mesuré :
  (a) un code exécuté qui imprime `os.getuid()` rend une valeur **≠ 0** ; (b) `while True: pass`
  meurt sur `RLIMIT_CPU` en moins du plafond fixé ; (c) l'écriture d'un fichier de 1 Go échoue ;
  (d) `open('/data/user/echohub-v2/…', 'w')` hors du bac est refusé ; (e) deux conversations
  différentes écrivent dans deux dossiers différents.

### L3 — Artefacts dans le fil

- **Produit** : outil `presenter_fichier` ; carte d'artefact dans le fil ; modale **agrandissable**
  (extension de `Modal.tsx:21-25`) ; en-tête à deux icônes code/aperçu, **désactivé-avec-raison**
  pour Python et texte brut ; aperçu HTML en `iframe sandbox` + `srcdoc` ; extension de
  `coloration.ts:33-38` à HTML et CSS.
- **Précondition** : L0 et L2 fusionnés.
- **Vérification** : `bun run typecheck` propre ; Playwright — ouvrir une conversation, cliquer
  l'artefact, la modale s'ouvre et s'agrandit, l'interrupteur bascule, `browser_get_console_errors`
  **vide**, capture archivée dans `logs/screenshots/`. Vérifier dans le DOM que l'`iframe` ne porte
  **pas** `allow-same-origin`.

### L4 — Pièces jointes transmises au modèle

- **Produit** : composeur acceptant collage, glisser-déposer et sélection ; liaison
  message ↔ fichiers ; `MessageInference.pieces` ; `content: str | list[PartieContenu]`
  (`contrat.py:119`) et `texte_de()` ; chargement du projecteur détecté par
  `fichiers_projecteurs()` et `chat_handler=MTMDChatHandler(...)` dans
  `adaptateur_llama_cpp.py:261`.
- **Précondition** : L0 fusionné.
- **Vérification** : `pytest backend -q` vert (l'union ne casse rien) ; `bun run typecheck` propre ;
  puis, **en conteneur**, charger `Qwen3-VL-2B-Instruct` avec son `mmproj`, envoyer une image dont
  le contenu est connu, et **coller la réponse du modèle dans le rapport de lot**. C'est le seul
  critère qui prouve la chaîne complète.

### L5 — Coût en tokens d'une image, mesuré

- **Produit** : `compter_multimodal` (via `mtmd_tokenize`, `mtmd_cpp.py:474`, et
  `mtmd_input_chunk_get_n_tokens`, `:486`) ; poste `IMAGES` dans `PosteContexte` et son miroir
  `frontend/src/chat/contexte/postes.ts`.
- **Précondition** : L4 fusionné.
- **Vérification** : la même image mesurée deux fois rend **le même nombre** ; une image deux fois
  plus grande rend un nombre **différent et supérieur** ; sans projecteur chargé, la réponse est
  `possible=false` avec sa raison — **jamais 0**. Les trois nombres figurent dans le rapport de lot.

### L6 — Repli honnête sans tour de vision

- **Produit** : le comportement décrit en 2.4 — image remplacée par une ligne factuelle **dans le
  message**, journalisation, et **aucun** texte d'interface.
- **Précondition** : L4 fusionné.
- **Vérification** : charger un modèle **sans** `mmproj`, envoyer une image ; l'envoi n'est pas
  bloqué, la génération se fait, **le modèle répond de lui-même**. Assertion Playwright : le DOM ne
  contient aucune chaîne du type « ne prend pas en charge », « non supporté », « unsupported ».

### L7 — Mesure réelle du MoE 35B-A3B — **DÉCISION OPÉRATEUR REQUISE**

- **Produit** : chargement du 35B-A3B avec et sans déport d'experts ; relevé VRAM occupée, RAM,
  débit ; comparaison au plan calculé et réponse à la question « le déport récupère-t-il les 6 Go
  inutilisés ? ».
- **Précondition — bloquante** : le volume `echohub_echohub_models` est **vide**, et le modèle vit
  dans `/mnt/models` (arborescence de la v1). Il faut trancher entre **(a)** monter `/mnt/models`
  en lecture seule dans le conteneur (rapide, zéro copie, mais fait dépendre la v2 d'un chemin
  hôte que `core/config.py` s'interdit précisément de coder en dur — donc à passer par
  `MODELS_DIR` et un volume déclaré dans le compose), et **(b)** copier ~20 Go dans le volume
  (78 Go libres : ça tient, mais c'est autant de moins pour le reste). **Recommandation : (a)**,
  en lecture seule, réversible d'une ligne.
- **Vérification** : le journal de chargement contient les lignes de déport que `CollecteurJournal`
  (`experts_hote.py:203`) exige déjà — un déport non confirmé est déjà traité comme un échec par le
  code ; tableau VRAM/RAM/débit avec et sans déport dans le rapport de lot.

### L8 — GGUF multipart éprouvé

- **Produit** : tests unitaires sur `parts_du_meme_modele` (`download_selection.py:37`) —
  aujourd'hui **zéro** — et un vrai téléchargement d'un dépôt découpé.
- **Précondition** : aucune (indépendant des deux chantiers).
- **Vérification** : `pytest backend -q` vert avec les nouveaux tests ; puis un téléchargement réel
  d'un petit modèle en deux parts : les deux fichiers arrivent, la progression couvre le total des
  parts (`download_selection.py:84-86`), et le modèle apparaît **entier** dans l'inventaire disque.

### L9 — Cadence du sondage du profil machine

- **Produit** : `INTERVALLE_PROFIL_MS` (`useProfilMachine.ts:18`) porté de 2 000 à une valeur entre
  10 000 et 15 000, **choisie après mesure du coût réel de `/api/systeme/profil` en conteneur**
  (en natif il est de 29 ms au premier appel, 16 ms ensuite : ce n'est pas là que se trouve le
  problème, la cause est le cycle `nvmlInit`/`nvmlShutdown` de `nvml.py:122` et `:132` répété 30
  fois par minute et par onglet).
- **Précondition** : aucune.
- **Vérification** : chronométrer `curl` sur `/api/systeme/profil` dans le conteneur (valeur dans
  le rapport) ; onglet réseau : le nombre de requêtes par minute correspond à la nouvelle cadence.

### L10 — Trois points de backlog courts

- **Produit** : (a) réglage de désactivation des CUDA graphs, transporté par `variables_env`
  (`contrat.py:95`) et appliqué par `_appliquer_environnement`
  (`adaptateur_llama_cpp.py:249`) ; (b) suppression de la ré-émission d'appels d'outil — retirer
  `tools` au second tour, c'est-à-dire ne plus repasser `outils` à `superviseur.generer`
  (`inference/__init__.py:243`) après un tour ayant produit des résultats ; (c) imposition de la
  langue de réponse dans le socle (`socle.py`).
- **Précondition** : aucune. **(b) doit passer après L1** pour éviter un conflit sur le même
  fichier.
- **Vérification** : (a) le journal de chargement montre la variable posée, et le modèle charge ;
  (b) conversation réelle où le modèle appelle un outil, reçoit les résultats et **ne redemande pas
  d'outil** — transcription dans le rapport, et le test doit être validé dans les deux sens ;
  (c) trois questions posées en français à un modèle qui répondait en anglais, toutes en français.

### L11 — Authentification sur le LAN — **DÉCISION OPÉRATEUR, RIEN À FAIRE SANS ELLE**

Le port 37920 est publié sur toutes les interfaces (`docker-compose.yml:46`) et **il n'y a aucune
authentification** : le CORS de `main.py:107` ne protège que des navigateurs, pas d'un `curl`
depuis le LAN. Trois voies possibles, toutes structurantes, **aucune ne doit être choisie par une
équipe d'exécution** : (a) ne publier que sur `127.0.0.1` et passer par un tunnel pour tout accès
distant ; (b) un mot de passe unique avec session signée ; (c) un proxy d'authentification devant
nginx. Le choix engage l'ergonomie quotidienne et le modèle de menace : il appartient à l'opérateur.

### L12 — Nettoyage disque — **DÉCISION OPÉRATEUR**

Ce qui est **mesuré** aujourd'hui : `echohub:gpu` 17,2 Go, `nvidia/cuda:12.8.0-devel` 14,6 Go,
`nvidia/cuda:12.8.0-base` 400 Mo, volumes `echohub_echohub_models` et `echohub_echohub_userdata`
à 0, **78 Go libres sur 476**. Le chiffre de « ~57 Go récupérables » du TODO n'a **pas** pu être
reproduit, et sa mention d'« espace libre 837 Go » ne correspond à rien sur cette machine. Toute
suppression touche des images et des volumes qui peuvent appartenir à la v1 **qui tourne** :
c'est une opération destructive sur des identités à établir une par une, pas un lot d'exécution.
L'opérateur doit désigner nommément ce qui part.

---

## Questions laissées ouvertes

1. **L7 (accès aux modèles)** — bind mount en lecture seule ou copie dans le volume ? La
   recommandation est le bind mount ; la décision reste à l'opérateur car elle touche la promesse
   de `core/config.py` (« aucun chemin absolu codé en dur »).
2. **L11 (authentification)** — trois voies, aucune tranchée.
3. **L12 (nettoyage)** — quelles images et quels volumes exactement, nommés un par un.
4. **`unshare --net` dans le bac** — à trancher sur mesure du coût de démarrage, au sein de L2. Si
   le coût est prohibitif, la règle est d'écrire que le réseau n'est pas coupé, pas de le prétendre.
5. **`.data-native`** — le résidu demandé au nettoyage vit dans `/mnt/projects/echohub-v2/.data-native`
   (204 Ko : une base SQLite vide, son WAL, un `backend.log`), **hors du worktree de cette équipe**.
   Sa suppression a été refusée par le plancher de déni. Aucun processus ne l'utilise (aucun port
   3792x en écoute, aucun descripteur ouvert) : `rm -rf /mnt/projects/echohub-v2/.data-native` est
   sans risque, à faire depuis le dépôt principal.
