"""Commands that talk to the real terminal over a serial port.

    python3 -m totem monitor --port /dev/cu.usbserial-XXXX
    python3 -m totem probe   --port ...
    python3 -m totem learn   --port ...
    python3 -m totem serial  --port ... --profile ff

Settings default to 1200 baud, 7 bits, even parity, 1 stop bit (7E1).
"""
from __future__ import annotations

import select
import sys
import time

from .app import App, INDICE, RIPETIZ
from .saver import Screensaver
from .settings import Settings
from .shop import Shop
from .text import set_ascii_only
from .terminal import (KEY_NAMES, KeyDecoder, KeyWatcher, PROFILES, SerialTerminal, load_keymap,
                       open_port, save_keymap, to_ascii)


def add_port_args(ap) -> None:
    ap.add_argument("--port", required=True,
                    help="serial device, e.g. /dev/cu.usbserial-0001")
    ap.add_argument("--baud", type=int, default=1200)
    ap.add_argument("--bits", type=int, default=7, choices=(7, 8))
    ap.add_argument("--parity", default="E", choices=("N", "E", "O"))
    ap.add_argument("--stop", type=int, default=1, choices=(1, 2))
    ap.add_argument("--keymap", default="keymap.json")


def _open(args):
    return open_port(args.port, args.baud, args.bits, args.parity, args.stop)


def cmd_monitor(args) -> None:
    """Show every byte the Minitel sends. Press keys on it and read the hex."""
    port = _open(args)
    print(f"In ascolto su {args.port} ({args.baud} {args.bits}{args.parity}{args.stop}). "
          "Ctrl+C per uscire.")
    try:
        while True:
            data = port.read(64)
            if data:
                print(f"{time.strftime('%H:%M:%S')}  {data.hex(' '):<24} {data!r}")
    except KeyboardInterrupt:
        pass


def _capture(port) -> bytes | None:
    """Wait for a key on the Minitel; returns None if the Mac keyboard is used."""
    buf = b""
    last = None
    while True:
        ready, _, _ = select.select([sys.stdin, port], [], [], 0.1)
        if sys.stdin in ready:
            sys.stdin.readline()
            return None
        if port in ready:
            chunk = port.read(64)
            if chunk:
                buf += chunk
                last = time.monotonic()
        if buf and last and time.monotonic() - last > 0.3:
            return buf


def cmd_learn(args) -> None:
    """Teach the totem which bytes each Minitel key sends."""
    port = _open(args)
    keymap = load_keymap(args.keymap)
    names = args.names or KEY_NAMES
    unknown = [n for n in names if n not in KEY_NAMES]
    if unknown:
        sys.exit(f"Tasti sconosciuti: {', '.join(unknown)}. Quelli validi: {', '.join(KEY_NAMES)}")
    print("Per ogni tasto: premilo sul Minitel. Se non invia nulla, premi Invio "
          "sul Mac per saltarlo; Ctrl+C per salvare e uscire.\n")
    try:
        for name in names:
            port.reset_input_buffer()
            print(f"Premi {name} ... ", end="", flush=True)
            seq = _capture(port)
            if seq is None:
                print("saltato")
                continue
            clash = [k for k, v in keymap.items() if seq in v and k != name]
            print(f"{seq.hex(' ')}  {seq!r}" + (f"   (uguale a {clash[0]}!)" if clash else ""))
            keymap[name] = [seq]
    except KeyboardInterrupt:
        pass
    save_keymap(args.keymap, keymap)
    print(f"\nSalvato in {args.keymap}")


def cmd_probe(args) -> None:
    """Send each control profile in turn and see which one the screen obeys."""
    port = _open(args)
    for name, p in PROFILES.items():
        text = to_ascii(f"Profilo {name}: la scritta e' qui? a' e' i' o' u' EUR")
        if p["goto"]:
            out = p["clear"] + p["goto"](10, 20) + text.encode()
        else:
            out = p["clear"] + b"\r\n" + text.encode() + b"\r\n"
        port.write(out)
        port.flush()
        print(f"Inviato '{name}'. Cosa vedi sul Minitel? (Invio = prossimo, q = esci) ",
              end="", flush=True)
        if sys.stdin.readline().strip().lower() == "q":
            break
    print("\nRicorda il profilo che ha pulito lo schermo e posizionato il testo: "
          "e' quello da usare con --profile.")


def cmd_baudtest(args) -> None:
    """Try faster speeds on the real terminal (see totem/baudtest.py)."""
    from . import baudtest
    port = _open(args)
    print(f"Prova velocita': {args.hold:.0f} s per passo. Guarda lo schermo e annota quali righe leggi.")
    baudtest.run(port, args.hold, args.only)
    print("Finito: porta e terminale di nuovo a 1200 baud.")


def cmd_serial(args) -> None:
    set_ascii_only(True)   # accents and euro are spelled out before the layout is computed
    shop = Shop(args.store, cache_dir=args.cache)
    settings = Settings(args.settings, saver_after=args.saver, idle_after=args.idle,
                        ink=args.saver_ink)
    app = App(shop, width=args.width, loading_delay=args.loading_delay, settings=settings)
    term = SerialTerminal(_open(args), args.profile, 0, args.baud)
    decoder = KeyDecoder(load_keymap(args.keymap))
    saver = Screensaver(args.width, settings.saver_after, settings.ink, hold=settings.hold)
    # During the screensaver any key matters (it wakes it); otherwise only the keys that would
    # change the screen being drawn interrupt the drawing.
    watcher = KeyWatcher(term.port, decoder,
                         log=lambda seq: print(f"[sequenza non riconosciuta: {seq.hex(' ')}]", file=sys.stderr),
                         is_command=lambda k: saver.active or app.accepts(k))
    interrupted = watcher.interrupted     # asked between the pieces of every drawing
    app.on_loading = lambda rows: term.try_draw(rows, abort=interrupted)
    parity = {"E": "pari", "O": "dispari", "N": "nessuna"}[args.parity]
    app.line_info = f"{args.baud} baud, {args.bits} bit, parità {parity}, {args.stop} stop"
    print(f"Totem attivo su {args.port}, profilo {args.profile}. Ctrl+C per uscire.",
          file=sys.stderr)
    secs = term.try_draw(app.screen(), full=True, abort=interrupted)
    print(f"[disegno schermata: ~{secs:.1f}s]", file=sys.stderr)
    last = time.monotonic()
    try:
        while True:
            data = term.read()
            keys = watcher.take()                # first the commands that came during a drawing
            keys += decoder.feed(data) if data else decoder.flush()
            for seq in decoder.take_unknown():
                print(f"[sequenza non riconosciuta: {seq.hex(' ')}]", file=sys.stderr)
            now = time.monotonic()
            saver.configure(settings.saver_after, settings.ink, settings.hold)   # live changes
            if keys and saver.wake():
                # The key that wakes the screensaver is not a command: just bring back
                # the screen that was showing.
                print("[screensaver: sveglia]", file=sys.stderr)
                last = now
                secs = term.try_draw(app.screen(), full=True, abort=interrupted)
                print(f"[disegno: ~{secs:.1f}s]", file=sys.stderr)
                continue
            idle = settings.idle_after > 0 and now - last > settings.idle_after
            if not keys and idle and len(app.stack) > 1 and not saver.active:
                keys = [INDICE]
            if not keys:
                frame = saver.tick(now, last)
                if frame is not None:
                    term.try_draw(frame, abort=interrupted)
                continue
            last = now
            for k in keys:
                print(f"[tasto {k}]", file=sys.stderr)
                app.key(k)
            # Ripetiz. redraws everything: handy if the terminal was just switched on
            # or the screen got scrambled.
            secs = term.try_draw(app.screen(), full=args.full or RIPETIZ in keys, abort=interrupted)
            print(f"[disegno: ~{secs:.1f}s]", file=sys.stderr)
    except KeyboardInterrupt:
        pass
