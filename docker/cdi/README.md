# Spec CDI NVIDIA — régénération au boot

Le numéro majeur de `/dev/nvidia-uvm` est assigné dynamiquement à chaque boot.
`/etc/cdi/nvidia.yaml` le fige au moment de sa génération, et Docker construit
les nœuds du conteneur depuis ce fichier. Quand le major change, CUDA meurt dans
le conteneur (`failed to initialize CUDA: unknown error`) et EchoHub ne charge
plus rien — mesuré le 2026-08-28, spec vieux de 18 jours, major 235 → 234.

Deux gardes, installées sur le PC fixe le 2026-08-28 :

- `echohub-cdi.service` (systemd, `Before=docker.service`) exécute
  `echohub-cdi-regenerer` à chaque boot, avant que le conteneur ne démarre.
- `start.sh --docker` appelle le même script et force la recréation du
  conteneur quand le spec a été régénéré.

Installation sur une autre machine :

```bash
sudo install -m 755 docker/cdi/echohub-cdi-regenerer /usr/local/sbin/
sudo install -m 644 docker/cdi/echohub-cdi.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now echohub-cdi.service
```

Le script est idempotent : il compare le major figé au major réel et ne
régénère qu'en cas d'écart (code 3), sinon ne touche à rien (code 0).
