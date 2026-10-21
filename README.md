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
python3 -m totem serial  --port ... --profile ff          # avvia il totem
```

A 1200 baud una schermata piena impiega circa 8-11 secondi: per questo la schermata
di caricamento è volutamente minima e `--profile ansi` / `vt52` (se il terminale li
capisce) ridisegnano solo le righe cambiate.

## Cablaggio (misure fatte sulla presa DIN a 5 poli)

Presa femmina a 180° vista dal davanti, chiave in alto:

| Posizione | Tensione |
|---|---|
| in basso al centro | massa (collegata alla schermatura) |
| alto destra, basso destra | 4 V (candidati per l'uscita dati) |
| alto sinistra | 2,9 V (candidato per l'ingresso dati) |
| basso sinistra | **13,4 V, alimentazione ausiliaria: non collegarla mai** |

Adattatore USB-TTL (Waveshare FT232RNL) con selettore su **5 V**: massa → massa,
filo dati del Minitel → RXD dell'adattatore. Per provare il verso opposto (TXD verso
il Minitel) usare un resistore da 1 kΩ in serie. Non collegare il VCC dell'adattatore.
Quale filo sia TX e quale RX è ancora da confermare con `monitor`.

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

- Test sul Minitel vero: velocità accettata, profilo di controllo, tasti, caratteri accentati.
- Se il terminale accetta velocità più alte, passarci (da 1200 a 9600 baud la schermata
  scende da ~10 s a ~1 s).
- Avvio automatico sul Raspberry Pi e ritorno al menu dopo inattività (già previsto: `--idle`).
