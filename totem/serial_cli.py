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

from .app import App, INDICE
from .shop import Shop
from .terminal import (KEY_NAMES, KeyDecoder, PROFILES, SerialTerminal, load_keymap,
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
    print("Per ogni tasto: premilo sul Minitel. Se non invia nulla, premi Invio "
          "sul Mac per saltarlo; Ctrl+C per salvare e uscire.\n")
    try:
        for name in KEY_NAMES:
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


def cmd_serial(args) -> None:
    shop = Shop(args.store, cache_dir=args.cache)
    app = App(shop, width=args.width, loading_delay=args.loading_delay)
    term = SerialTerminal(_open(args), args.profile, 0, args.baud)
    app.on_loading = lambda rows: term.draw(rows)
    parity = {"E": "pari", "O": "dispari", "N": "nessuna"}[args.parity]
    app.line_info = f"{args.baud} baud, {args.bits} bit, parità {parity}, {args.stop} stop"
    decoder = KeyDecoder(load_keymap(args.keymap))
    print(f"Totem attivo su {args.port}, profilo {args.profile}. Ctrl+C per uscire.",
          file=sys.stderr)
    secs = term.draw(app.screen(), full=True)
    print(f"[disegno schermata: ~{secs:.1f}s]", file=sys.stderr)
    last = time.monotonic()
    try:
        while True:
            data = term.read()
            keys = decoder.feed(data) if data else decoder.flush()
            idle = time.monotonic() - last > args.idle and args.idle > 0
            if not keys and idle and len(app.stack) > 1:
                keys = [INDICE]
            if not keys:
                continue
            last = time.monotonic()
            for k in keys:
                print(f"[tasto {k}]", file=sys.stderr)
                app.key(k)
            secs = term.draw(app.screen(), full=args.full)
            print(f"[disegno: ~{secs:.1f}s]", file=sys.stderr)
    except KeyboardInterrupt:
        pass
