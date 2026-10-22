# ITOMItel

Totem informativo con il catalogo di ITOMI.shop su un terminale Videotel
**Philips HCS 80/08** (SIP), collegato a un Raspberry Pi via porta seriale.
Il programma legge in tempo reale il catalogo pubblico del negozio Shopify e lo
mostra in schermate a 80 colonne × 24 righe.

Solo libreria standard di Python 3.9+; `pyserial` serve solo per il collegamento
al terminale vero (`pip install -r requirements.txt`).

## Provarlo senza hardware

```bash
python3 -m totem                 # anteprima in console (80 colonne)
python3 -m totem --width 40      # versione compatta a 40 colonne
python3 -m totem web             # emulatore nel browser, fosfori verdi
```

Nell'anteprima in console: un numero sceglie la voce, un testo cerca; i tasti del
terminale si scrivono con i due punti (`:i` Indice, `:n` Seguente, `:p` Precedente,
`:a` Annul., `:c` Correzione, `:g` Guida, `:r` Ripetiz.).
`--keys '3|1|:n'` riproduce una sequenza senza interazione.

Nell'emulatore web: Home/F2 Indice, F1 Guida, Esc Annul., Backspace Correzione,
F5 Ripetiz., frecce o PgSu/PgGiù Precedente/Seguente, Invio. Si può simulare la
velocità di linea (1200 baud mostra quanto è lenta davvero).
Dopo ogni modifica al codice Python il server va riavviato.

## Collegarlo al Minitel

Impostazioni di partenza della seriale: 1200 baud, 7 bit, parità pari, 1 stop
(da confermare sul terminale). Terminale in modalità **Ascii 80 col** (voce 4 del
menu di accensione).

```bash
python3 -m totem monitor --port /dev/cu.usbserial-XXXX   # mostra i byte che invia il Minitel
python3 -m totem probe   --port ...                       # prova i profili di controllo schermo
python3 -m totem learn   --port ...                       # impara i tasti → keymap.json
python3 -m totem serial  --port /dev/serial0              # avvia il totem (profilo ansi)
```

A 1200 baud una schermata piena impiega circa 8-11 secondi: per questo la schermata
di caricamento è volutamente minima e `--profile ansi` / `vt52` (se il terminale li
capisce) ridisegnano solo le righe cambiate.

## Cablaggio (verificato sul campo, 2026-10-22)

Presa DIN a 5 poli femmina a 180° vista dal davanti, chiave in alto. Fili del cavo
MIDI tagliato (stessa posizione dei pin misurati):

| Filo | Tensione a riposo | Ruolo |
|---|---|---|
| esterno | 0 V | massa |
| **rosso** | 4 V (sorgente debole) | **ingresso dati del terminale**: il Pi trasmette qui (testato) |
| bianco | 4 V (sorgente debole) | non usato |
| **nero** | 0,1 V (collettore aperto) | **uscita dei tasti**: richiede un richiamo (pull-up) dal Pi |
| giallo | **13,4 V** | alimentazione ausiliaria: **non collegarla mai** |

Le linee sono TTL con resistenza interna di 6-10 kΩ circa, quindi un partitore da
3 kΩ le fa crollare. Il Pi 3 usa **/dev/serial0** (UART PL011, Bluetooth disattivato
con `dtoverlay=disable-bt`) a 3,3 V:

**Cablaggio definitivo, senza breadboard né resistori** (verificato 2026-10-22):

| Dal Minitel | Al Raspberry Pi |
|---|---|
| filo esterno (massa) | pin 6 (GND) |
| filo rosso (ingresso dati) | pin 8 (GPIO14, TXD) |
| filo nero (uscita tasti) | pin 10 (GPIO15, RXD) |

Bianco e giallo (13,4 V) restano isolati. Funziona perché il rosso è un ingresso con richiamo
debole (non può spingere corrente nel Pi) e il nero è a collettore aperto: il richiamo lo fa il
pull-up interno di GPIO15 (controllabile con `pinctrl get 15`). Se i tasti dovessero perdere
colpi, aggiungere un resistore da 10 kΩ tra pin 10 e pin 1 (3,3 V). Durante i test erano usati
1 kΩ in serie su entrambi i fili e 10 kΩ di richiamo.

Terminale in modalità **Ascii 80 col** (voce 4 del
menu di accensione).

```bash
python3 -m totem monitor --port /dev/cu.usbserial-XXXX   # mostra i byte che invia il Minitel
python3 -m totem probe   --port ...                       # prova i profili di controllo schermo
python3 -m totem learn   --port ...                       # impara i tasti → keymap.json
python3 -m totem serial  --port /dev/serial0              # avvia il totem (profilo ansi)
```

A 1200 baud una schermata piena impiega circa 8-11 secondi: per questo la schermata
di caricamento è volutamente minima e `--profile ansi` / `vt52` (se il terminale li
capisce) ridisegnano solo le righe cambiate.

## Cablaggio (verificato sul campo, 2026-10-22)

Presa DIN a 5 poli femmina a 180° vista dal davanti, chiave in alto. Fili del cavo
MIDI tagliato (stessa posizione dei pin misurati):

| Filo | Tensione a riposo | Ruolo |
|---|---|---|
| esterno | 0 V | massa |
| **rosso** | 4 V (sorgente debole) | **ingresso dati del terminale**: il Pi trasmette qui (testato) |
| bianco | 4 V (sorgente debole) | non usato |
| **nero** | 0,1 V (collettore aperto) | **uscita dei tasti**: richiede un richiamo (pull-up) dal Pi |
| giallo | **13,4 V** | alimentazione ausiliaria: **non collegarla mai** |

Le linee sono TTL con resistenza interna di 6-10 kΩ circa, quindi un partitore da
3 kΩ le fa crollare. Il Pi 3 usa **/dev/serial0** (UART PL011, Bluetooth disattivato
con `dtoverlay=disable-bt`) a 3,3 V:

- Pi → Minitel: pin 8 (TXD) → resistore 1 kΩ → filo rosso. Funziona a 1200 baud 7E1.
- Minitel → Pi: filo **nero** → resistore 1 kΩ → pin 10 (RXD), più un resistore 10 kΩ dal pin 10
  al pin 1 (3,3 V) come richiamo: l'uscita è a collettore aperto. Pin 6 = massa comune.
  Funziona: `learn` ha riconosciuto tutti i tasti e il catalogo si naviga dalla tastiera del Minitel.

Terminale in modalità **Ascii 80 col**: con `probe` il profilo **ansi** (ESC[2J, ESC[r;cH,
ESC[K) pulisce e posiziona il testo; la prima schermata completa compare in 4-5 secondi.

## Avvio automatico sul Raspberry Pi

Dopo aver copiato il progetto in `~/ITOMItel` (utente `itomitel`) e aver fatto `learn`:

```bash
sudo cp ~/ITOMItel/deploy/itomitel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now itomitel
```

Il totem parte all'accensione e si riavvia da solo se si ferma. Log: `journalctl -u itomitel -f`.
Dopo aver aggiornato il codice: `sudo systemctl restart itomitel`. Se il Minitel viene acceso dopo
il Pi, il tasto Ripetiz. ridisegna tutta la schermata.

## Struttura

| File | Cosa fa |
|---|---|
| `totem/shop.py` | client di sola lettura per `products.json` e `collections.json`, con cache su disco |
| `totem/app.py` | schermate e navigazione (macchina a stati, indipendente dal terminale) |
| `totem/logo.py` | logo ITOMI in ASCII (griglia 21 × 12 moduli) |
| `totem/terminal.py` | codifica schermo → byte ASCII e byte → tasti, con aggiornamento a righe |
| `totem/serial_cli.py` | comandi `serial`, `monitor`, `probe`, `learn` |
| `totem/web.py`, `totem/web/index.html` | emulatore nel browser |
| `tests/` | test senza hardware né rete: `python3 -m unittest discover tests` |

Per cambiare le voci della home o il testo dei Credits: `HOME_ITEMS` e `CREDITS_TEXT`
in `totem/app.py`.

## Ancora da fare

- Caratteri accentati sul terminale vero (ora si scrivono come `e'`, `EUR`).
- Se il terminale accetta velocità più alte, passarci (da 1200 a 9600 baud la schermata
  scende da ~10 s a ~1 s).
- Avvio automatico sul Raspberry Pi e ritorno al menu dopo inattività (già previsto: `--idle`).
