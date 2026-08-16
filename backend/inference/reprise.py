"""Reprise d'une réponse que le moteur a coupée avant qu'elle soit complète.

Extrait de `backend/inference/__init__.py` : ces constantes et leur justification y avaient fait
dépasser le module. Elles ne décident de rien — c'est `MoteurChat._diffuser_complet` qui reprend —
mais elles portent la mesure qui a motivé le mécanisme, et elles se lisent mieux ensemble.
"""

from __future__ import annotations

# Reprise d'une réponse coupée par la fenêtre du moteur.
#
# MESURÉ le 2026-08-16 : sur un contexte de 2 048, le moteur rend 1 980 tokens puis
# `finish_reason = "length"`. L'adaptateur le SAIT — il pose la raison sur son morceau de fin — mais
# personne ne la lisait : la chaîne ne rendait que `texte`, `tokens_generes` et `tokens_par_seconde`.
# La réponse s'arrêtait donc en plein milieu d'une phrase, sans que rien ne le signale. Et quand la
# coupure tombait au milieu d'un `<tool_call>`, le JSON devenait illisible, aucun appel n'était
# détecté, et le balisage restait dans la réponse.
#
# Une réponse ne doit JAMAIS s'arrêter avant d'être complète : tant que le moteur dit l'avoir coupée
# par manque de place, on la reprend là où elle s'est arrêtée.
CONTINUATIONS_MAX = 4

# En dessous de ce nombre de tokens libres, reprendre ne produirait rien : `create_chat_completion`
# calcule son plafond à `n_ctx - taille du prompt`, et le prompt de la reprise contient déjà tout ce
# qui a été écrit. On le dit alors clairement, au lieu de boucler sur des tours vides.
MARGE_CONTINUATION_TOKENS = 256

# Rédigée en anglais comme le socle, et pour la même raison mesurée : ces modèles suivent mieux une
# consigne de forme dans la langue de leur raisonnement. Elle n'entre jamais dans l'affichage.
CONSIGNE_REPRISE = (
    "Your previous message was cut off mid-way because the output limit was reached. Continue it "
    "from exactly where it stopped — mid-sentence, even mid-word if that is where it ended. Do not "
    "repeat anything already written, do not restart, do not summarise, do not apologise. Write "
    "only the continuation."
)

# Dit à l'UTILISATEUR, dans le fil, quand la fenêtre est réellement pleine. Une remédiation qui
# existe : le contexte se choisit au chargement du modèle. Laisser une phrase coupée net sans un mot
# serait exactement le défaut corrigé ici.
AVERTISSEMENT_FENETRE_PLEINE = (
    "\n\n*[Réponse interrompue : la fenêtre de contexte du modèle est pleine. "
    "Recharger le modèle avec un contexte plus grand, ou repartir d'une nouvelle conversation.]*"
)
