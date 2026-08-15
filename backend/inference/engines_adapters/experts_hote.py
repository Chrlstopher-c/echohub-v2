"""Rappel des tenseurs d'experts en mémoire hôte, côté llama.cpp.

ÉCART ASSUMÉ ENTRE LE PLAN ET L'API PYTHON — relevé sur `llama_cpp` 0.3.34 réellement installé dans
l'image, jamais supposé :

- `Llama.__init__` n'expose AUCUN paramètre de placement par tenseur : ni `override_tensor`, ni
  `n_cpu_moe`, ni `tensor_buft_overrides`. Sa signature se termine par `**kwargs`, **jamais consulté
  dans le corps**. Vérifié à l'exécution : `Llama(model_path=…, n_cpu_moe=20)` construit un objet
  sans exception ni avertissement, et ne déporte rien. Une implémentation qui passerait par là
  aurait l'air de fonctionner tout en ne faisant strictement rien — c'est le piège principal ici.
- Aucun binaire `llama-server` / `llama-cli` n'est présent dans l'image : la route sous-processus
  vers la CLI, qui elle expose `-ot` et `--n-cpu-moe`, n'existe pas.
- La route réelle, prouvée par mesure, est le champ C `llama_model_params.tensor_buft_overrides`.
  Le binding le déclare `c_void_p` avec le commentaire « NOTE: unused » — donc jamais rempli, mais à
  la bonne position ABI. `Llama.__init__` construit `self.model_params` via
  `llama_model_default_params()` puis le consomme dans la même méthode, sans point d'accroche
  intermédiaire : le seul moyen de remplir le champ sans patcher le paquet est de remplacer
  temporairement cette fonction. `llama.py` fait `import llama_cpp.llama_cpp as llama_cpp`, donc le
  remplacement y est visible, et `__init__` ne réécrit jamais ce champ.

Mesure de référence sur le 0.5B : le journal imprime simultanément « offloaded 25/25 layers to GPU »
et « tensor blk.20.ffn_down.weight buffer type overridden to CUDA_Host », et le tampon modèle CUDA0
passe de 373,73 à 304,76 MiB — exactement le poids des tenseurs visés. Les deux mécanismes se
composent : on met `n_gpu_layers` au nombre total de blocs ET on rappelle des tenseurs en hôte.

TROIS GARDES, parce qu'une erreur ici corrompt silencieusement la mémoire du chargement :

1. la disposition de `llama_model_params` est vérifiée — taille de la struct et décalage du champ —
   avant tout écrit. Une mise à jour du paquet qui réordonnerait la struct ferait écrire un pointeur
   dans le mauvais champ : on refuse la stratégie plutôt que de charger ;
2. la struct d'override est déclarée ici. Celle du binding, `llama_model_tensor_override`, est
   l'override de QUANTIFICATION (`{c_char_p, c_int}`) : la réutiliser décalerait l'ABI de 4 octets ;
3. le déport n'est JAMAIS réputé appliqué. Le journal de chargement doit porter une ligne
   « buffer type overridden » pour chaque bloc visé, sinon le chargement est déclaré échoué.
"""

from __future__ import annotations

import ctypes
import logging
import re
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

# Disposition mesurée sur llama_cpp 0.3.34. Ce ne sont pas des choix : ce sont les valeurs relevées
# par `ctypes.sizeof` et `.offset` sur la struct du binding, et elles servent de garde.
TAILLE_MODEL_PARAMS_ATTENDUE = 72
DECALAGE_OVERRIDES_ATTENDU = 8
NOM_CHAMP_OVERRIDES = "tensor_buft_overrides"

# Marqueurs du journal de llama.cpp. Ce sont les seuls canaux de vérification disponibles : le
# binding ne rend aucun compte-rendu de placement.
MARQUEUR_SURCHARGE = "buffer type overridden"
MARQUEUR_TAMPON = "compute buffer size"
LIGNES_TAMPONS_MAX = 32

# Journaux candidats : llama-cpp-python route le journal C vers `logging`. Le nom exact a changé
# entre versions, on se branche donc aussi sur la racine plutôt que de parier sur un seul.
NOMS_JOURNAUX = ("llama-cpp-python", "llama_cpp", "")

MOTIF_BLOC = re.compile(r"blk\.(\d+)\.")

# Le remplacement de `llama_model_default_params` est global au processus : deux chargements
# simultanés se voleraient leurs surcharges. Le superviseur les sérialise déjà, ce verrou est la
# ceinture — il est pris avec un délai borné, jamais indéfiniment.
_VERROU_SURCHARGES = threading.Lock()
DELAI_VERROU_SURCHARGES_S = 30.0

# Chemins d'accès connus vers la bibliothèque ggml déjà chargée par le paquet.
_CHEMINS_BIBLIOTHEQUE: tuple[tuple[str, ...], ...] = (
    ("_ggml", "_lib"),
    ("_ggml", "lib"),
    ("llama_cpp", "_lib"),
)


class SurchargeBufferTenseur(ctypes.Structure):
    """`llama_model_tensor_buft_override` : `{const char* pattern; ggml_backend_buffer_type_t buft}`.

    Déclarée ici et non reprise du binding : la classe homonyme de `llama_cpp` est l'override de
    quantification, dont le second champ est un `c_int`. La confondre décale tout le tableau.
    """

    _fields_ = [("pattern", ctypes.c_char_p), ("buft", ctypes.c_void_p)]


class SupportDeport(BaseModel):
    """Ce que le paquet installé permet réellement — mesuré à chaud, jamais présumé."""

    model_config = ConfigDict(frozen=True)

    disponible: bool
    raison: str = ""
    buffer_type_hote: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def verifier_support(module: Any) -> SupportDeport:
    """Contrôle l'ABI et les symboles nécessaires AVANT tout écrit dans la struct C.

    Toute divergence rend un refus nommé plutôt qu'une tentative : écrire un pointeur au mauvais
    décalage ne lèverait aucune exception et corromprait le chargement en silence.
    """
    parametres = getattr(module, "llama_model_params", None)
    if parametres is None or not issubclass(parametres, ctypes.Structure):
        return SupportDeport(disponible=False, raison="`llama_model_params` introuvable dans le binding.")

    taille = ctypes.sizeof(parametres)
    champ = getattr(parametres, NOM_CHAMP_OVERRIDES, None)
    decalage = getattr(champ, "offset", None)
    if taille != TAILLE_MODEL_PARAMS_ATTENDUE or decalage != DECALAGE_OVERRIDES_ATTENDU:
        return SupportDeport(
            disponible=False,
            raison=(
                f"Disposition de `llama_model_params` inattendue : {taille} octets et décalage "
                f"{decalage} au lieu de {TAILLE_MODEL_PARAMS_ATTENDUE} et "
                f"{DECALAGE_OVERRIDES_ATTENDU}. Écrire ici viserait un autre champ."
            ),
            details={"taille": taille, "decalage": decalage},
        )
    if not callable(getattr(getattr(module, "llama_cpp", None), "llama_model_default_params", None)):
        return SupportDeport(disponible=False, raison="`llama_model_default_params` non atteignable.")

    buft = _buffer_type_hote(module)
    if not buft:
        return SupportDeport(
            disponible=False,
            raison="`ggml_backend_cpu_buffer_type` introuvable ou nul dans la bibliothèque ggml chargée.",
        )
    return SupportDeport(disponible=True, buffer_type_hote=buft, details={"taille_model_params": taille})


def _buffer_type_hote(module: Any) -> int | None:
    """Pointeur du buffer type hôte de ggml, résolu dans la bibliothèque déjà chargée.

    Le prototype est fixé explicitement : sans `restype`, ctypes tronquerait la valeur de retour à
    un entier 32 bits et rendrait un pointeur invalide sur les adresses hautes.
    """
    bibliotheque = _bibliotheque_ggml(module)
    if bibliotheque is None:
        return None
    try:
        fonction = bibliotheque.ggml_backend_cpu_buffer_type
        fonction.argtypes = []
        fonction.restype = ctypes.c_void_p
        return fonction()
    except (AttributeError, OSError) as exc:
        logger.warning("Buffer type hôte ggml non résolu : {}", exc)
        return None


def _bibliotheque_ggml(module: Any) -> ctypes.CDLL | None:
    """Première bibliothèque ctypes atteignable parmi les chemins connus du paquet."""
    for chemin in _CHEMINS_BIBLIOTHEQUE:
        courant: Any = module
        for attribut in chemin:
            courant = getattr(courant, attribut, None)
            if courant is None:
                break
        if isinstance(courant, ctypes.CDLL):
            return courant
    return None


def motif_experts(index_bloc: int) -> str:
    """Motif `std::regex` ciblant les trois tenseurs d'experts d'un bloc, et eux seuls.

    Le point séparateur est échappé et suivi immédiatement du reste du nom : sans cela `blk.1.`
    attraperait aussi `blk.11.`. Les motifs sont construits à partir d'entiers produits par le
    planificateur, jamais d'une saisie : une expression invalide ferait échouer le chargement en C.
    """
    return rf"blk\.{int(index_bloc)}\.ffn_(gate|up|down)_exps"


class Surcharges:
    """Tableau ctypes des surcharges et les motifs encodés qu'il pointe, gardés vivants ensemble.

    Les deux doivent survivre jusqu'au retour de `Llama()` : le C ne copie ni le tableau ni les
    chaînes, il en garde les adresses. Les tenir dans un même objet rend cette durée de vie explicite
    au lieu de dépendre du hasard des références locales.
    """

    def __init__(self, indices: tuple[int, ...], buffer_type: int) -> None:
        self.motifs: list[bytes] = [motif_experts(index).encode("utf-8") for index in indices]
        self.tableau = (SurchargeBufferTenseur * (len(self.motifs) + 1))()
        for position, motif in enumerate(self.motifs):
            self.tableau[position].pattern = motif
            self.tableau[position].buft = buffer_type
        # Entrée terminale à `pattern` NULL : c'est ainsi que llama.cpp borne le parcours du tableau.
        self.tableau[len(self.motifs)].pattern = None
        self.tableau[len(self.motifs)].buft = None

    @property
    def pointeur(self) -> ctypes.c_void_p:
        return ctypes.cast(self.tableau, ctypes.c_void_p)


class CollecteurJournal(logging.Handler):
    """Capte le journal de chargement de llama.cpp pour VÉRIFIER le déport au lieu de le supposer.

    Deux voies de captation, pas une seule — **mesuré** sur `llama_cpp` 0.3.34, pas supposé (voir
    `_installer_relais_c`) :

    1. `brancher()` s'attache à `logging`, où la documentation du paquet affirme que le journal C est
       routé. C'était vrai historiquement, ce n'est plus le fait mesuré : `llama_cpp/_logger.py`
       installe au chargement du module un callback C qui fait `print(text, file=sys.stderr)` —
       jamais `logger.log(...)`. `logger.level` n'y sert que de condition au `print`, aucun
       `logging.Handler` ne reçoit donc jamais ces lignes. Un chargement avec déport échouait à
       100 % sur cette machine avant ce correctif, alors que le journal brut (`docker logs`) portait
       bien les lignes `buffer type overridden` : le déport avait réellement lieu, seule sa preuve
       n'atteignait jamais ce collecteur.
    2. `_installer_relais_c()` remplace donc, en plus, le callback C lui-même le temps du
       chargement — la route que le commentaire d'origine évitait « pour rester réversible » : elle
       l'est tout autant, restaurée dans `_retirer_relais_c()`, et c'est la seule qui reçoive
       réellement le texte sur cette version du paquet.

    Le handler n'échoue jamais — une exception levée depuis un `emit` pendant un chargement se
    perdrait sur une sortie standard justement mise en sourdine par le moteur.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.blocs_surcharges: set[int] = set()
        self.lignes_tampons: list[str] = []
        self._niveaux: list[tuple[logging.Logger, int]] = []
        # Callback C de relais et référence à l'original, gardés vivants tant qu'installés : le C ne
        # garde que leurs adresses, un objet ctypes collecté ferait pointer `llama_log_set` dans le
        # vide (même risque que `Surcharges.tableau`, documenté plus haut dans ce module).
        self._callback_relais: Any = None
        self._callback_original: Any = None
        self._tampon_texte_c: str = ""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - un journal illisible ne doit pas interrompre un chargement
            return
        self._analyser_ligne(message)

    def _analyser_ligne(self, message: str) -> None:
        if MARQUEUR_SURCHARGE in message:
            trouve = MOTIF_BLOC.search(message)
            if trouve is not None:
                self.blocs_surcharges.add(int(trouve.group(1)))
        elif MARQUEUR_TAMPON in message and len(self.lignes_tampons) < LIGNES_TAMPONS_MAX:
            self.lignes_tampons.append(message.strip())

    def _capter_texte_c(self, texte: str) -> None:
        """Reçoit un fragment brut du callback C, où une ligne peut arriver en plusieurs morceaux."""
        self._tampon_texte_c += texte
        *lignes, reste = self._tampon_texte_c.split("\n")
        self._tampon_texte_c = reste
        for ligne in lignes:
            self._analyser_ligne(ligne)

    def brancher(self) -> None:
        """S'attache aux journaux candidats et abaisse leur seuil le temps du chargement."""
        for nom in NOMS_JOURNAUX:
            journal = logging.getLogger(nom) if nom else logging.getLogger()
            self._niveaux.append((journal, journal.level))
            journal.addHandler(self)
            journal.setLevel(logging.DEBUG)

    def debrancher(self) -> None:
        """Rend les journaux à leur état d'origine, y compris le seuil posé par le moteur."""
        for journal, niveau in self._niveaux:
            journal.removeHandler(self)
            journal.setLevel(niveau)
        self._niveaux.clear()

    def installer_relais_c(self, module: Any) -> None:
        """Remplace le callback C tant que la voie `logging` n'est pas confirmée réceptrice.

        Dégrade silencieusement si le binding n'expose pas ce qu'il faut : le collecteur reste
        fonctionnel via `brancher()` seul, exactement comme avant ce correctif.
        """
        cible = getattr(module, "llama_cpp", None)
        type_callback = getattr(cible, "llama_log_callback", None)
        installateur = getattr(cible, "llama_log_set", None)
        if cible is None or type_callback is None or not callable(installateur):
            return
        journal_module = getattr(module, "_logger", None)
        original = getattr(journal_module, "llama_log_callback", None)

        def _relais(niveau: int, texte: bytes, donnee_utilisateur: Any) -> None:  # noqa: ARG001
            try:
                self._capter_texte_c(texte.decode("utf-8", errors="replace"))
            except Exception:  # noqa: BLE001 - un callback C qui lève termine le processus
                return

        try:
            self._callback_relais = type_callback(_relais)
            installateur(self._callback_relais, ctypes.c_void_p(0))
            self._callback_original = original
        except (AttributeError, TypeError, OSError) as exc:
            logger.warning("Relais du journal C llama.cpp non installé : {}", exc)
            self._callback_relais = None

    def retirer_relais_c(self, module: Any) -> None:
        """Restaure le callback C d'origine, sinon `llama_cpp._logger` reste muet après ce chargement."""
        if self._callback_relais is None or self._callback_original is None:
            self._callback_relais = None
            return
        cible = getattr(module, "llama_cpp", None)
        installateur = getattr(cible, "llama_log_set", None) if cible is not None else None
        if callable(installateur):
            try:
                installateur(self._callback_original, ctypes.c_void_p(0))
            except (AttributeError, TypeError, OSError) as exc:
                logger.warning("Restauration du journal C llama.cpp échouée : {}", exc)
        self._callback_relais = None


@contextmanager
def deport_actif(module: Any, indices: tuple[int, ...], buffer_type: int) -> Iterator[CollecteurJournal]:
    """Rend `llama_model_default_params` porteuse des surcharges, le temps d'UN chargement.

    Le remplacement est global au processus : il est sérialisé et restauré dans un `finally`, sinon
    un second chargement hériterait des surcharges du premier.
    """
    surcharges = Surcharges(indices, buffer_type)
    cible = module.llama_cpp
    originale = cible.llama_model_default_params

    def parametres_surcharges() -> Any:
        parametres = originale()
        setattr(parametres, NOM_CHAMP_OVERRIDES, surcharges.pointeur)
        return parametres

    if not _VERROU_SURCHARGES.acquire(timeout=DELAI_VERROU_SURCHARGES_S):
        raise TimeoutError("Un autre chargement occupe déjà les surcharges de tenseurs.")
    collecteur = CollecteurJournal()
    try:
        cible.llama_model_default_params = parametres_surcharges
        collecteur.brancher()
        collecteur.installer_relais_c(module)
        yield collecteur
    finally:
        collecteur.retirer_relais_c(module)
        collecteur.debrancher()
        cible.llama_model_default_params = originale
        # `surcharges` reste référencé jusqu'ici : le C a lu ses adresses pendant tout le bloc.
        del surcharges
        _VERROU_SURCHARGES.release()


def verifier_application(collecteur: CollecteurJournal, indices: tuple[int, ...]) -> tuple[bool, str]:
    """Confronte les blocs visés à ceux que le journal déclare effectivement rappelés en hôte.

    On exige au moins une ligne par bloc visé, pas un nombre exact de tenseurs : le fichier peut ne
    pas porter les trois tenseurs d'experts sur chaque bloc, et l'exiger inventerait une contrainte.
    Un journal muet est traité comme un déport non appliqué — l'absence de preuve n'en est pas une.
    """
    manquants = sorted(set(indices) - collecteur.blocs_surcharges)
    if not collecteur.blocs_surcharges:
        return False, (
            "Le journal de llama.cpp ne porte aucune ligne de surcharge de buffer : impossible de "
            "vérifier que les experts sont bien en mémoire hôte, le chargement est refusé."
        )
    if manquants:
        return False, (
            f"Blocs {manquants} demandés en mémoire hôte mais absents du journal de chargement : "
            "leurs experts sont restés en VRAM."
        )
    return True, f"{len(indices)} groupes d'experts confirmés en mémoire hôte par le journal."
