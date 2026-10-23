# ITOMItel

> **In English:** ITOMItel turns a vintage Philips HCS 80/08 Videotel/Minitel-style terminal
> into a kiosk that browses and searches a Shopify store's public catalogue. A Raspberry Pi
> talks to the terminal over its serial port (three wires, no adapter) and renders every screen
> as 80x24 ASCII with ANSI cursor codes at 1200 baud. Pure Python 3 standard library (plus
> `pyserial`), with a browser emulator and tests that need no hardware. Code MIT licensed;
> ITOMI is a registered trademark (see [TRADEMARK.md](TRADEMARK.md)).

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

Impostazioni della seriale: 1200 baud, 7 bit, parità pari, 1 stop. Il terminale va messo in
modalità **Ascii 80 col** (voce 4 del menu che compare premendo Indice, dopo l'elenco
telefonico dell'accensione).

```bash
python3 -m totem monitor --port /dev/serial0   # mostra i byte che invia il Minitel
python3 -m totem probe   --port /dev/serial0   # prova i profili di controllo schermo
python3 -m totem learn   --port /dev/serial0   # impara i tasti → keymap.json
python3 -m totem serial  --port /dev/serial0   # avvia il totem (profilo ansi)
```

Con un adattatore USB-seriale la porta è del tipo `/dev/cu.usbserial-XXXX`.

Il profilo **ansi** (ESC[2J, ESC[r;cH, ESC[K) è quello che il terminale capisce. A 1200 baud una
schermata piena impiega circa 7-9 secondi (volutamente lenta, come un Minitel vero): per questo la
schermata di caricamento è minima e si ridisegnano solo le righe cambiate.

## Cablaggio (verificato sul campo, 2026-10-22)

Presa DIN a 5 poli femmina a 180° vista dal davanti, chiave in alto. Fili del cavo MIDI tagliato:

| Filo | Tensione a riposo | Ruolo |
|---|---|---|
| esterno | 0 V | massa |
| **rosso** | 4 V (sorgente debole) | **ingresso dati del terminale**: il Pi trasmette qui |
| bianco | 4 V (sorgente debole) | non usato |
| **nero** | 0,1 V (collettore aperto) | **uscita dei tasti** |
| giallo | **13,4 V** | alimentazione ausiliaria: **non collegarla mai** |

Il Pi 3 usa **/dev/serial0** (UART PL011 a 3,3 V, Bluetooth disattivato con
`dtoverlay=disable-bt`). Collegamento definitivo, **senza breadboard né resistori**:

| Dal Minitel | Al Raspberry Pi |
|---|---|
| filo esterno (massa) | pin 6 (GND) |
| filo rosso (ingresso dati) | pin 8 (GPIO14, TXD) |
| filo nero (uscita tasti) | pin 10 (GPIO15, RXD) |

Bianco e giallo restano isolati. Funziona perché le linee del terminale hanno una resistenza
interna alta (6-10 kΩ circa): il rosso non può spingere corrente nel Pi, e il nero è a collettore
aperto, con il richiamo fatto dal pull-up interno di GPIO15 (controllabile con `pinctrl get 15`).
Se i tasti dovessero perdere colpi, aggiungere un resistore da 10 kΩ tra pin 10 e pin 1 (3,3 V).
Durante i test erano usati 1 kΩ in serie su entrambi i fili. Con un partitore a resistori bassi
(es. 1 kΩ + 2 kΩ) le linee crollano: evitarlo.

## Screensaver

Dopo 5 minuti senza tasti il Minitel mostra il logo ITOMI **in negativo** (il logo è "scavato" in un
campo di `#`), centrato e costruito riga per riga: fermo per 30 secondi, poi si cancella dal basso e
lo schermo resta vuoto per 20 secondi, in ciclo. Un tasto qualsiasi lo interrompe e riporta la
schermata di prima; **quel tasto non vale come comando**. Un ciclo completo costa circa 1,2 KB (10 s
di trasmissione a 1200 baud). Opzioni di `serial`: `--saver SECONDI` (default 300, 0 = mai) e
`--saver-ink CARATTERE` per cambiare il riempimento. Dopo 2 minuti di inattività il totem torna
prima alla home (`--idle`). Nell'emulatore web c'è il menu "Screensaver" e il pulsante
"Prova screensaver". Il codice è in `totem/saver.py`.

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
| `totem/saver.py` | screensaver: logo in negativo costruito a righe |
| `totem/web.py`, `totem/web/index.html` | emulatore nel browser |
| `tests/` | test senza hardware né rete: `python3 -m unittest discover tests` |

Per cambiare le voci della home o il testo dei Credits: `HOME_ITEMS` e `CREDITS_TEXT`
in `totem/app.py`.

## Ancora da fare

- Caratteri accentati sul terminale vero (ora si scrivono come `e'`, `EUR`).
- Verificare sul terminale vero lo screensaver; se supporta il video inverso (ESC[7m), il logo in negativo
  potrebbe essere a blocchi pieni invece che di `#`.

## Usarlo con un altro negozio Shopify

Basta cambiare l'indirizzo: `python3 -m totem serial --store https://IL-TUO-NEGOZIO.myshopify.com ...`
(vale anche per `python3 -m totem` e `python3 -m totem web`). Funziona con qualunque negozio che
esponga i JSON pubblici `products.json` e `collections.json` (la maggior parte dei negozi non
protetti da password). Testi, logo e menu si cambiano in `totem/app.py` e `totem/logo.py`.

## Contribuire

Segnalazioni e proposte sono benvenute: apri una issue o una pull request. Prima di inviare,
fai girare i test (`python3 -m unittest discover tests`): non richiedono hardware né rete.

## Licenza

Il **codice** è rilasciato con licenza **MIT** (vedi [LICENSE](LICENSE)): puoi usarlo, modificarlo e
ridistribuirlo, anche per scopi commerciali, mantenendo l'indicazione di copyright.

**ITOMI È UN MARCHIO D'IMPRESA REGISTRATO IN ITALIA - REGISTRAZIONE #302023000068748/2023**

Il nome ITOMI/ITOMItel e il logo appartengono a ITOMI.studio e non sono coperti dalla licenza MIT:
se riusi il progetto per un altro negozio, sostituisci nome e logo con i tuoi (dettagli in
[TRADEMARK.md](TRADEMARK.md)).

Componenti di terzi: [pyserial](https://github.com/pyserial/pyserial) (licenza BSD-3-Clause,
solo per il collegamento al terminale); il tipo di carattere non è incluso:
l'emulatore nel browser carica [VT323](https://fonts.google.com/specimen/VT323) (SIL Open Font
License) da Google Fonts e, se non è raggiungibile, usa un carattere monospazio di sistema.
