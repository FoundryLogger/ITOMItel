import json
import threading
import time
import unittest
import urllib.request

from totem.web import make_server


class FakeShop:
    def __init__(self, delay=0.0):
        self.delay = delay

    def collections(self):
        return []

    def refresh(self):
        pass

    def newest(self):
        time.sleep(self.delay)
        return []

    def search(self, q):
        return []


class WebTests(unittest.TestCase):
    def start(self, shop, loading_delay=0.5):
        server = make_server(shop, "127.0.0.1", 0, loading_delay)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.read()

    def key(self, key, sid="t", width=80):
        req = urllib.request.Request(
            self.base + "/api/key", method="POST",
            data=json.dumps({"sid": sid, "width": width, "key": key}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    def test_serves_the_page(self):
        self.start(FakeShop())
        html = self.get("/").decode()
        self.assertIn("ITOMItel", html)
        self.assertIn("/api/key", html)

    def test_screen_and_keys(self):
        self.start(FakeShop())
        first = json.loads(self.get("/api/screen?sid=t&width=80"))
        self.assertEqual(len(first["rows"]), 24)
        self.assertEqual({len(r) for r in first["rows"]}, {80})
        self.assertFalse(first["busy"])
        credits = self.key("0")
        self.assertTrue(credits["rows"][0].startswith("CREDITS"))
        back = self.key("ANNUL")
        self.assertEqual(back["rows"][0], "ITOMItel".center(80))

    def test_width_40_is_its_own_session(self):
        self.start(FakeShop())
        self.key("0", width=80)
        narrow = json.loads(self.get("/api/screen?sid=t&width=40"))
        self.assertEqual({len(r) for r in narrow["rows"]}, {40})
        self.assertEqual(narrow["rows"][0], "ITOMItel".center(40))

    def test_slow_fetch_answers_with_loading_then_the_result(self):
        self.start(FakeShop(delay=0.4), loading_delay=0.05)
        r = self.key("2")
        self.assertTrue(r["busy"])
        self.assertIn("Caricamento in corso...", "\n".join(r["rows"]))
        for _ in range(40):
            time.sleep(0.05)
            r = json.loads(self.get("/api/screen?sid=t&width=80"))
            if not r["busy"]:
                break
        self.assertFalse(r["busy"])
        self.assertIn("Nessun prodotto", "\n".join(r["rows"]))

    def test_bad_keys_are_rejected(self):
        self.start(FakeShop())
        for bad in ("", "evil", "indice"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.key(bad)
            self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
