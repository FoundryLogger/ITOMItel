"""Console preview of the totem: python3 -m totem

Type a number or text and press Enter. Keys of the terminal are typed with
a colon: :i indice, :n seguente, :p precedente, :a annul, :c correzione,
:g guida, :r ripetiz. A line of plain text is typed one character at a time
followed by Invio. Use --keys to replay a sequence non-interactively.
"""
import argparse
import errno
import sys
from pathlib import Path

from .app import (ANNUL, CORREZIONE, GUIDA, INDICE, INVIO, PRECEDENTE, RIPETIZ,
                  SEGUENTE, App)
from .shop import Shop

ALIASES = {"i": INDICE, "n": SEGUENTE, "p": PRECEDENTE, "a": ANNUL,
           "c": CORREZIONE, "g": GUIDA, "r": RIPETIZ, "v": INVIO}


def show(app: App) -> None:
    rows = app.screen()
    edge = "+" + "-" * len(rows[0]) + "+"
    print(edge)
    for r in rows:
        print("|" + r + "|")
    print(edge)


def feed(app: App, token: str) -> None:
    if token.startswith(":"):
        app.key(ALIASES.get(token[1:], token[1:].upper()))
    else:
        for ch in token:
            app.key(ch)
        app.key(INVIO)


def serial_main(cmd: str) -> None:
    from . import serial_cli
    from .terminal import PROFILES

    ap = argparse.ArgumentParser(prog=f"totem {cmd}")
    serial_cli.add_port_args(ap)
    if cmd == "learn":
        ap.add_argument("names", nargs="*", metavar="TASTO",
                        help="learn only these keys, e.g. DESTRA SINISTRA (default: all)")
    if cmd == "baudtest":
        ap.add_argument("--hold", type=float, default=12.0, help="seconds each step stays on screen")
        ap.add_argument("--only", type=int, help="run just this step (1-6)")
    if cmd == "serial":
        ap.add_argument("--store", default="https://itomi.myshopify.com")
        ap.add_argument("--cache", default=str(Path(__file__).parent.parent / "cache"))
        ap.add_argument("--profile", default="ansi", choices=sorted(PROFILES),
                        help="terminal control codes (ansi works on the HCS 80/08)")
        ap.add_argument("--width", type=int, default=80, choices=(40, 80),
                        help="columns of the terminal's Ascii mode")
        ap.add_argument("--idle", type=int, default=None,
                        help="seconds of inactivity before going back to the menu (0 = never); "
                             "default: the saved setting (120)")
        ap.add_argument("--loading-delay", type=float, default=0.5,
                        help="seconds before the loading screen appears (0 = always)")
        ap.add_argument("--saver", type=int, default=None,
                        help="seconds of inactivity before the screensaver starts (0 = never); "
                             "default: the saved setting (300)")
        ap.add_argument("--saver-ink", default=None,
                        help="character that fills the negative logo (default: the saved setting, #)")
        ap.add_argument("--settings", default="settings.json",
                        help="where the Impostazioni screen saves its values")
        ap.add_argument("--full", action="store_true",
                        help="always redraw the whole screen")
    args = ap.parse_args(sys.argv[2:])
    getattr(serial_cli, f"cmd_{cmd}")(args)


def web_main() -> None:
    import webbrowser

    from .web import make_server

    ap = argparse.ArgumentParser(prog="totem web",
                                 description="Browser emulator of the terminal")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--store", default="https://itomi.myshopify.com")
    ap.add_argument("--cache", default=str(Path(__file__).parent.parent / "cache"))
    ap.add_argument("--loading-delay", type=float, default=0.5,
                    help="seconds before the loading screen appears (0 = always)")
    ap.add_argument("--no-open", action="store_true", help="don't open the browser")
    args = ap.parse_args(sys.argv[2:])
    try:
        server = make_server(Shop(args.store, cache_dir=args.cache), "127.0.0.1",
                             args.port, args.loading_delay)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        sys.exit(f"La porta {args.port} è già occupata, probabilmente da un emulatore "
                 f"ancora acceso (con il codice vecchio).\n"
                 f"Fermalo con Ctrl+C nel terminale dove gira, oppure:\n"
                 f"  lsof -ti :{args.port} | xargs kill\n"
                 f"Oppure usa un'altra porta: python3 -m totem web --port {args.port + 1}")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Emulatore su {url}  (Ctrl+C per fermarlo)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        return web_main()
    if len(sys.argv) > 1 and sys.argv[1] in ("serial", "monitor", "learn", "probe", "baudtest"):
        return serial_main(sys.argv[1])
    ap = argparse.ArgumentParser(prog="totem")
    ap.add_argument("--store", default="https://itomi.myshopify.com")
    ap.add_argument("--cache", default=str(Path(__file__).parent.parent / "cache"))
    ap.add_argument("--width", type=int, default=80, choices=(40, 80),
                    help="screen width in columns")
    ap.add_argument("--loading-delay", type=float, default=0.5,
                    help="seconds before the loading screen appears (0 = always)")
    ap.add_argument("--keys", help="replay tokens separated by '|', e.g. '1|:n|2'")
    args = ap.parse_args()

    app = App(Shop(args.store, cache_dir=args.cache), width=args.width,
              loading_delay=args.loading_delay)

    def on_loading(rows):
        print("\n[schermata di caricamento]")
        edge = "+" + "-" * len(rows[0]) + "+"
        print(edge)
        for r in rows:
            print("|" + r + "|")
        print(edge)

    app.on_loading = on_loading
    show(app)
    if args.keys:
        for token in args.keys.split("|"):
            print(f"\n>>> {token}")
            feed(app, token)
            show(app)
        return
    for line in sys.stdin:
        feed(app, line.rstrip("\n"))
        show(app)


if __name__ == "__main__":
    main()
