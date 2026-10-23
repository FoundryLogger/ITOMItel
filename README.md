# ITOMItel

> **In English:** ITOMItel turns a vintage Philips HCS 80/08 Videotel/Minitel-style terminal
> into a kiosk. A Raspberry Pi talks to the terminal over its serial port (three wires, no
> adapter) and renders every screen as 80x24 ASCII with ANSI cursor codes at 1200 baud. It
> browses and searches a Shopify store's public catalogue, reads articles from two WordPress
> sites and RAI Televideo (text only), and has a screensaver and a settings screen. Pure
> Python 3 standard library (plus `pyserial`), a browser emulator, and tests that need no
> hardware. Code MIT licensed; ITOMI is a registered trademark (see [TRADEMARK.md](TRADEMARK.md)).

Totem informativo su un terminale Videotel **Philips HCS 80/08** (SIP), collegato a un Raspberry Pi
via porta seriale. In schermate a 80 colonne × 24 righe mostra il **catalogo di ITOMI.shop** (negozio
Shopify, letto in tempo reale), le **Storie di EPIC** e le **Guide Nerdvana** (due siti WordPress),
il **Televideo RAI**, i Credits con la scheda tecnica, le Impostazioni e uno screensaver.

Solo libreria standard di Python 3.9+; `pyserial` serve solo per il collegamento
al terminale vero (`pip install -r requirements.txt`).

## Il menu principale

Due colonne: a sinistra **1** Sfoglia Catalogo, **2** Novità, **3** Bestseller, **4** In offerta,
**5** Cerca un prodotto; a destra **6** Storie di EPIC, **7** Guide Nerdvana, **8** Televideo RAI,
**9** Impostazioni, **0** Credits (la decima voce è lo zero, come sul tastierino di un telefono).
Voci e ordine sono in `HOME_ITEMS` in `totem/app.py`.

## I tasti

| Tasto del Minitel | Cosa fa |
|---|---|
| **numeri** e **lettere** | scelgono la voce: negli elenchi 1-9 e poi A-J (19 per pagina, maiuscole o minuscole); nel Televideo si digitano le 3 cifre della pagina |
| **Seguente**, freccia **→** | pagina successiva |
| **Precedente**, freccia **←** | pagina precedente; dalla prima pagina torna indietro di una schermata |
| **Annul.** | indietro di una schermata (nella ricerca cancella prima il testo scritto) |
| **Indice** | torna al menu principale |
| **Correzione** | cancella una lettera |
| **Guida** | aiuto; da lì **1** apre le Impostazioni |
| **Ripetiz.** | ridisegna tutta la schermata e rilegge i dati |
| **Invio** | conferma la ricerca |
| **0** | nelle pagine di Storie e Guide: torna all'indice del sito |

**Mentre il Minitel sta ricevendo una schermata** (a 1200 baud ci vogliono 7-9 secondi) **un comando valido
per quella schermata la interrompe** e parte subito la schermata del comando nuovo, disegnata per intero da
capo (sul terminale c'è una schermata a metà, quindi non si può mandare solo la differenza). "Valido" vuol
dire che il tasto, in quella schermata, cambia davvero qualcosa: una voce del menu, una pagina che esiste,
Annul., Indice (non nel menu stesso), Ripetiz. Non interrompono il disegno un tasto che lì non fa niente
(una lettera nel menu, Seguente sull'ultima pagina, una voce che non esiste) né i byte sconosciuti: i tasti
inutili non si perdono, vengono eseguiti nell'ordine a disegno finito. Durante lo screensaver qualsiasi tasto
lo ferma. La regola è `App.accepts()` (con un metodo `accepts` per ogni schermata) e un test la confronta, per
ogni schermata e ogni tasto, con quello che il tasto fa davvero. Per renderlo possibile il disegno parte a
pezzi di circa 0,2 secondi, mai spezzati dentro una sequenza di controllo, e tra un pezzo e l'altro si
controlla la porta (`KeyWatcher` e `SerialTerminal.draw` in `totem/terminal.py`). Un tasto premuto durante la
schermata di caricamento viene eseguito appena i dati sono arrivati. Premere più comandi di seguito li esegue
tutti, nell'ordine, e disegna solo l'ultima schermata.

Le frecce su e giù non fanno nulla. Le schermate di lettura vanno a pagine intere: lo scorrimento per
riga, che farebbe ridisegnare tutto lo schermo a ogni pressione (oltre 10 secondi a 1200 baud), è stato
provato con le sequenze di cancella/inserisci riga del terminale e scartato.

## Gli elenchi

Catalogo, prodotti, Storie, città e guide sono elenchi a **una riga per voce**, 19 per pagina (le 19
righe del corpo dello schermo), con l'indice **1-9 e poi A-J**: quando le voci di una pagina sono più di
nove, la riga di suggerimento dice "Premi il numero o la lettera". Nei prodotti il prezzo è a destra
("da 6,99EUR" se le varianti costano diverso, "offerta 9,99EUR" per un prezzo scontato, "esaurito"). I
tasti `K`-`Z` e lo `0` non scelgono niente negli elenchi. Il codice è in `INDEX_KEYS`, `chosen()` e
`LIST_PER_PAGE` in `totem/app.py`.

## Provarlo senza hardware

```bash
python3 -m totem                 # anteprima in console (80 colonne)
python3 -m totem --width 40      # versione compatta a 40 colonne
python3 -m totem web             # emulatore nel browser, fosfori verdi
```

Nell'anteprima in console: un numero sceglie la voce, un testo cerca; i tasti del
terminale si scrivono con i due punti (`:i` Indice, `:n` Seguente, `:p` Precedente,
`:a` Annul., `:c` Correzione, `:g` Guida, `:r` Ripetiz., `:destra` e `:sinistra` le frecce).
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

**All'accensione** il terminale mostra il suo elenco telefonico e non ricorda la modalità: per usare il
totem premi **Indice → 4 (Ascii 80 col) → Ripetiz.**

I tasti arrivano come sequenze `ESC O x` (Indice `P`, Seguente `n`, Precedente `R`, Annul. `Q`,
Correzione `l`, Guida `m`, Ripetiz. `S`, Invio `M`), registrate in `keymap.json`: il file è nel
repository perché è la mappa di questo terminale (`learn TASTO …` impara solo i tasti che nomini). Le
frecce sono le sequenze ANSI standard (destra `ESC [ C`, sinistra `ESC [ D`) e il programma le conosce
di serie. Per scoprire un tasto nuovo senza fermare il servizio basta premerlo: la sequenza compare nel
registro del Pi come `[sequenza non riconosciuta: …]` (`journalctl -u itomitel`).

Il profilo **ansi** (ESC[2J, ESC[r;cH, ESC[K) è quello che il terminale capisce.

**Velocità: 1200 o 4800 baud**, a scelta nelle Impostazioni (voce 5). Il terminale parte sempre a 1200 e
il Pi gli chiede di cambiare con il comando dei Minitel, `ESC : k` seguito dal codice della velocità
(`v` = 4800, `d` = 1200): il comando esce alla vecchia velocità, il terminale risponde alla vecchia
velocità (il Pi legge e scarta la risposta) e dopo **1 secondo** il Pi passa alla nuova. All'avvio il Pi
chiede da solo la velocità salvata. Se il Minitel viene spento e riacceso torna a 1200: premendo
Indice, 4 e Ripetiz. il Pi riceve spazzatura (parla a 4800 mentre il terminale è a 1200), se ne accorge
(4 o più byte di controllo scartati in un colpo) e ricomincia da 1200 chiedendo di nuovo la velocità.
Il 23 ottobre 2026 la prima prova a 4800 era fallita perché dopo il comando si aspettava solo 0,6 secondi;
con 1 secondo funziona. 2400 e 9600 non sono stati verificati e non sono offerti. A 4800 baud una schermata
piena impiega circa 2 secondi invece di 8.

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

## Storie di EPIC e Guide Nerdvana

Due siti WordPress di ITOMI letti con l'API pubblica (`/wp-json/wp/v2/…`), sempre con la fonte
indicata nella schermata:

- **Voce 6, Storie di EPIC** (whatisepic.it): gli articoli della categoria *Storie*, dal più recente,
  19 per pagina con la data; si apre un articolo e si legge a pagine (Seguente/Precedente). Sotto il titolo
  e la data compare l'autore ("di Nome Cognome"), preso dal nome che WordPress gli dà.
- **Voce 7, Guide Nerdvana** (nerdvanaguides.com): prima si sceglie la **città** (Londra, Los Angeles,
  New York, Osaka, Tokyo, con il numero di guide), poi la guida in **ordine alfabetico** (la data di
  pubblicazione non significa niente qui, quindi non è mostrata) e infine si legge.

In tutte le loro pagine il tasto **0** torna all'**indice del sito**: l'elenco delle città per Nerdvana,
la prima pagina dell'elenco per le Storie (la riga dei tasti lo ricorda: "0=indice Nerdvana").
L'elenco si scarica subito, il testo di un articolo solo quando lo apri. Le risposte restano 10 minuti
in memoria e l'ultima copia sul disco (`cache/`), così si legge anche senza rete. Immagini, video e
audio non compaiono; i titoli di paragrafo sono in maiuscolo. Per aggiungere un altro sito WordPress
o cambiare categoria si modifica `WP_SOURCES` in `totem/app.py` (sito, categoria o `None` per far
scegliere la categoria, ordine, date sì/no, titoli) e si aggiunge una voce a `HOME_ITEMS`. Il codice
è in `totem/blog.py`.

## Televideo RAI

Voce **8** del menu. Mostra le pagine di RAI Televideo nella versione "solo testo" che RAI pubblica
sul web (`servizitelevideo.rai.it`, 40 colonne, centrate sullo schermo a 80). Si digitano **3 cifre**
(100-899) e la pagina si apre al terzo numero, come con il telecomando; **Seguente/Precedente** (o le frecce)
scorrono la pagina se è più lunga dello schermo, poi passano alla sottopagina e infine alla pagina
successiva o precedente. Niente colori né grafica a mosaico. Ogni schermata riporta la fonte
("Fonte: RAI Televideo - servizitelevideo.rai.it"). Il codice è in `totem/televideo.py`.

**I contenuti sono di RAI.** Il programma li legge **solo quando qualcuno li chiede**, li tiene in
memoria **al massimo 2 minuti** (mai su disco), aspetta 0,4 s tra una richiesta e l'altra e si
dichiara con uno User-Agent che rimanda a questo repository. Nessun testo di Televideo è nel
repository (i test usano pagine inventate). Prima di mostrarlo al pubblico verifica le condizioni
di riutilizzo di RAI: gli autori di questo progetto non le hanno trovate e non possono garantire
che l'uso sia consentito. Se vuoi disattivare la funzione, togli la voce `Televideo RAI` da
`HOME_ITEMS` in `totem/app.py`.

## Screensaver

Dopo 5 minuti senza tasti il Minitel riempie **tutto lo schermo di `#`** e lascia **vuoto solo il logo
ITOMI**, al centro (il logo è "scavato" nel riempimento). Lo schermo si riempie riga per riga dall'alto;
resta fermo per 30 secondi, poi si svuota dal basso e **ricomincia subito a riempirsi**, senza pause a schermo vuoto, in ciclo. Un tasto
qualsiasi lo interrompe e riporta la schermata di prima; **quel tasto non vale come comando**.
A 1200 baud la costruzione richiede circa 20 secondi (uno schermo pieno sono quasi 2 KB). Si regola
dalla schermata Impostazioni (vedi sotto) o con `--saver SECONDI` (0 = mai) e `--saver-ink CARATTERE`
all'avvio. Dopo 2 minuti di inattività il totem torna prima alla home (`--idle`). Nell'emulatore web
c'è il menu "Screensaver" e il pulsante "Prova screensaver". Il codice è in `totem/saver.py`.

## Impostazioni

Dal Minitel: voce **9** del menu, oppure **Guida → 1**. Ogni numero porta l'impostazione al valore successivo
(in giro, poi ricomincia): 1 screensaver dopo 1 / 5 / 10 minuti o mai, 2 ritorno alla home dopo
1 / 2 / 5 minuti o mai, 3 carattere di riempimento (`# @ X * + O`), 4 durata dello schermo pieno fermo (15 s,
30 s, 1 min, 2 min), 5 velocità della linea (1200 o 4800 baud, vedi sopra). I cambi valgono subito e restano salvati in `settings.json` (nella cartella del
programma, non è nel repository) anche dopo lo spegnimento del Pi. Le opzioni `--saver`, `--idle`
e `--saver-ink` di `serial` servono solo come valore di partenza; con `--settings FILE` si sceglie
un altro file. Nell'emulatore web la scelta dello screensaver segue quella delle Impostazioni.
Il codice è in `totem/settings.py`.

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

## Aggiornare il Pi

Dal Mac: `deploy/update-pi.sh` copia il codice sul Pi, fa girare lì i test e solo se passano riavvia
il totem (ferma il processo e systemd lo rilancia, senza `sudo`). Allinea anche le cancellazioni (un file
tolto dal progetto sparisce dal Pi) senza toccare `keymap.json`, `settings.json` e `cache/`. Serve un accesso SSH con chiave:
una volta sola, `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_itomitel` e
`ssh-copy-id -i ~/.ssh/id_ed25519_itomitel.pub itomitel@itomitel.local`, poi una voce `Host itomitel`
in `~/.ssh/config`. Il Minitel va riportato in Ascii 80 col dopo il riavvio (Ripetiz. ridisegna).

## Struttura

| File | Cosa fa |
|---|---|
| `totem/shop.py` | client di sola lettura per `products.json` e `collections.json`, con cache su disco |
| `totem/app.py` | schermate e navigazione (macchina a stati, indipendente dal terminale) |
| `totem/logo.py` | logo ITOMI in ASCII (griglia 21 × 12 moduli) |
| `totem/text.py` | da HTML a testo, caratteri non disponibili sul terminale (accenti, €), a capo |
| `totem/terminal.py` | codifica schermo → byte ASCII e byte → tasti, con aggiornamento a righe |
| `totem/serial_cli.py` | comandi `serial`, `monitor`, `probe`, `learn` |
| `totem/saver.py` | screensaver: schermo pieno di `#` con il logo scavato al centro |
| `totem/blog.py` | articoli e categorie di un sito WordPress (Storie EPIC, Nerdvana Guides) via API pubblica, con cache |
| `totem/televideo.py` | lettura di RAI Televideo (solo testo) su richiesta, con cache di 2 minuti |
| `totem/settings.py` | impostazioni modificabili dal Minitel, salvate in `settings.json` |
| `totem/web.py`, `totem/web/index.html` | emulatore nel browser |
| `deploy/` | servizio systemd e `update-pi.sh` |
| `keymap.json` | mappa dei tasti di questo Minitel |
| `tests/` | test senza hardware né rete: `python3 -m unittest discover tests` |

Per cambiare le voci della home o il testo dei Credits: `HOME_ITEMS` e `CREDITS_TEXT`
in `totem/app.py`.

## Ancora da fare

- Provare sul terminale vero i caratteri accentati (ora si scrivono come `e'`, `EUR`).
- Se il terminale supporta il video inverso (`ESC[7m`), il negativo dello screensaver potrebbe essere
  a blocchi pieni invece che di `#`, consumando meno fosforo.
- Verificare le condizioni di riutilizzo dei contenuti RAI prima di mostrare il Televideo al pubblico.

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
