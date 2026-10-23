#!/bin/sh
# Copia il programma sul Raspberry Pi, lancia i test lì e, solo se passano, riavvia il totem.
# Uso: deploy/update-pi.sh [host]      (host predefinito: itomitel, vedi ~/.ssh/config)
# Non cancella nulla sul Pi: keymap.json e settings.json restano quelli del Pi.
# Il riavvio ferma il processo: systemd (Restart=always) lo rilancia con il codice nuovo,
# così non serve sudo.
set -e
HOST="${1:-itomitel}"
cd "$(dirname "$0")/.."
rsync -a --exclude .git --exclude cache --exclude __pycache__ \
      --exclude keymap.json --exclude settings.json ./ "$HOST":~/ITOMItel/
ssh "$HOST" 'cd ~/ITOMItel && python3 -m unittest discover tests > /dev/null 2>&1 \
  && { pkill -f "[t]otem serial"; sleep 8; systemctl is-active itomitel; } \
  || echo "I test sul Pi non passano: il totem NON e stato riavviato."'
