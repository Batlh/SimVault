# Tests – Internet: Quellen, Anmeldungen, Downloads, Websuche, Browser, Captchas

from helpers import *  # noqa: F401,F403


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = {"plugin_folders": [self.tmp]}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write(self, name, text):
        with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_builtin(self):
        srcs, errors = sources.load_sources({"plugin_folders": []})
        ids = {s.id for s in srcs}
        self.assertTrue({"tsr", "curseforge", "patreon", "newsea"} <= ids)
        tsr = next(s for s in srcs if s.id == "tsr")
        self.assertEqual(tsr.search_url("Cool Hair"),
                         "https://www.thesimsresource.com/downloads/browse/category/sims4/search/Cool%20Hair/")
        self.assertTrue(tsr.can_search)                      # liefert echte Trefferlisten

    def test_json_python_override_and_errors(self):
        self._write("simsdom.json", json.dumps({"id": "SimsDom", "name": "SimsDom",
                                                "search_url": "https://simsdom.com/s?q={query}"}))
        self._write("tsr_fix.json", json.dumps([{"id": "tsr", "name": "TSR neu",
                                                 "search_url": "https://tsr.example/{query}"}]))
        self._write("voll.py", textwrap.dedent("""
            from simvault.web.sources.base import Source, SearchResult
            class Voll(Source):
                id = "voll"
                name = "Volle Quelle"
                needs_login = True
                def search(self, query, session=None):
                    return [SearchResult(title=query.upper(), url="https://x/1", source_id=self.id)]
        """))
        self._write("kaputt.py", "this is not python")
        self._write("zukunft.py", "REQUIRES_API = 99\n")
        self._write("ohne_query.json", json.dumps({"id": "x", "name": "X", "search_url": "https://x"}))
        self._write("_aus.json", json.dumps({"id": "aus", "name": "Aus", "search_url": "https://a/{query}"}))

        srcs, errors = sources.load_sources(self.cfg)
        by_id = {s.id: s for s in srcs}
        self.assertEqual(by_id["simsdom"].search_url("a b"), "https://simsdom.com/s?q=a+b")
        self.assertEqual(by_id["tsr"].name, "TSR neu")                     # ersetzt die mitgelieferte
        self.assertTrue(by_id["voll"].can_search)
        self.assertEqual(by_id["voll"].search("haare")[0].title, "HAARE")
        self.assertNotIn("aus", by_id)                                       # _-Dateien ignoriert
        failed = sorted(os.path.basename(p) for p, _m in errors)
        self.assertEqual(failed, ["kaputt.py", "ohne_query.json", "zukunft.py"])

    def test_enable_disable_and_links(self):
        cfg = {"plugin_folders": [], "sources_enabled": {"google": False, "tsr": True}}
        ids = {s.id for s in sources.enabled_sources(cfg)}
        self.assertNotIn("google", ids)
        links = cc_searcher.search_links("Cool_Hair.package", cfg)
        self.assertNotIn("Google", links)
        self.assertIn("Cool+Hair", links["CurseForge"])


@unittest.skipUnless(HAVE_CRYPTO, "cryptography nicht installiert")
class SecureStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_encrypted_roundtrip_and_tamper(self):
        from simvault.web import secure_store
        store = secure_store.SecureStore(self.tmp)
        cookie = {"name": "session_id", "value": "GEHEIM-12345", "domain": ".patreon.com", "path": "/",
                  "secure": True, "expires": 0}
        store.save("patreon", [cookie])
        with open(store.data_path, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"GEHEIM", raw)                        # nie im Klartext auf der Platte
        self.assertNotIn(b"patreon", raw)
        again = secure_store.SecureStore(self.tmp)               # neu geladen, gleicher Schlüssel
        self.assertEqual(again.cookies("patreon"), [cookie])
        self.assertEqual(again.logins()["patreon"]["domains"], ["patreon.com"])
        with open(store.data_path, "r+b") as f:                  # Manipulation fällt auf
            f.seek(-5, 2)
            f.write(b"XXXXX")
        with self.assertRaises(secure_store.StoreError):
            secure_store.SecureStore(self.tmp).cookies("patreon")
        os.remove(store.key_path)                                # anderer Schlüssel: nicht lesbar
        store2 = secure_store.SecureStore(self.tmp)
        with self.assertRaises(secure_store.StoreError):
            store2.cookies("patreon")

    def test_key_is_protected_by_callback(self):
        from simvault.web import secure_store
        store = secure_store.SecureStore(self.tmp, protect=(lambda k: b"P" + bytes(b ^ 0x55 for b in k),
                                                            lambda k: bytes(b ^ 0x55 for b in k[1:])))
        store.save("x", [{"name": "a", "value": "b", "domain": "x.com"}])
        with open(store.key_path, "rb") as f:
            self.assertTrue(f.read().startswith(b"P"))
        self.assertEqual(len(store.cookies("x")), 1)

    @unittest.skipUnless(os.name == "nt", "nur Windows (DPAPI)")
    def test_windows_dpapi(self):
        from simvault.web import secure_store
        blob = secure_store._dpapi(b"k" * 32, True)
        self.assertNotEqual(blob, b"k" * 32)
        self.assertEqual(secure_store._dpapi(blob, False), b"k" * 32)

    def test_cookie_header_rules(self):
        from simvault.web.secure_store import cookie_header
        cookies = [{"name": "a", "value": "1", "domain": ".patreon.com", "path": "/"},
                   {"name": "b", "value": "2", "domain": "www.patreon.com", "path": "/posts", "secure": True},
                   {"name": "c", "value": "3", "domain": "evilpatreon.com", "path": "/"}]
        self.assertEqual(cookie_header(cookies, "https://www.patreon.com/posts/123"), "a=1; b=2")
        self.assertEqual(cookie_header(cookies, "http://www.patreon.com/posts/123"), "a=1")
        self.assertEqual(cookie_header(cookies, "https://patreon.com/home"), "a=1")


class DownloadInstallTests(unittest.TestCase):
    def setUp(self):
        import zipfile
        self.tmp = tempfile.mkdtemp()
        self.mods = os.path.join(self.tmp, "Mods")
        self.tray = os.path.join(self.tmp, "Tray")
        os.makedirs(self.mods)
        os.makedirs(self.tray)
        self.have = os.path.join(self.mods, "Vorhanden.package")
        dbpf.write_package(self.have, [(dbpf.TYPE_CASP, 0, 0xA000000000000001, b"alt")])
        src = os.path.join(self.tmp, "src")
        os.makedirs(src)

        def pkg(name, instance):
            path = os.path.join(src, name)
            dbpf.write_package(path, [(dbpf.TYPE_CASP, 0, instance, b"casp" + name.encode())])
            return path

        new_pkg = pkg("Neues_Kleid.package", 0xB000000000000002)
        old_pkg = pkg("Schon_da.package", 0xA000000000000001)
        script = os.path.join(src, "Mod.ts4script")
        with zipfile.ZipFile(script, "w") as z:
            z.writestr("mod/__init__.pyc", b"x")
        inner = os.path.join(src, "innen.zip")
        with zipfile.ZipFile(inner, "w") as z:
            z.write(pkg("Haare.package", 0xB000000000000003), "Haare.package")
        self.archive = os.path.join(self.tmp, "Set.zip")
        with zipfile.ZipFile(self.archive, "w") as z:
            z.write(new_pkg, "Set/Neues_Kleid.package")
            z.write(old_pkg, "Set/Schon_da.package")
            z.write(script, "Set/Mod.ts4script")
            z.write(inner, "Set/Extras/innen.zip")
            z.writestr("Set/0x00000002!0x0000000000abcdef.trayitem", b"\x00" * 20)
            z.writestr("Set/0x00000000!0x0000000000abcdef.householdbinary", b"\x00" * 20)
            z.writestr("Set/LIESMICH.txt", "Viel Spaß")
            z.writestr("Set/kaputt.package", b"kein Paket")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_install_archive_places_everything_and_skips_known(self):
        from simvault.web import downloads
        result = downloads.install(self.archive, self.mods, self.tray)
        placed = {(k, os.path.relpath(p, self.tmp)) for k, p in result["installiert"]}
        base = os.path.join("Mods", downloads.INSTALL_SUBFOLDER)
        self.assertEqual(placed, {
            ("Paket", os.path.join(base, "Set", "Neues_Kleid.package")),
            ("Paket", os.path.join(base, "Set", "Haare.package")),
            ("Script", os.path.join(base, "Mod.ts4script")),
            ("Bibliothek", os.path.join("Tray", "0x00000002!0x0000000000abcdef.trayitem")),
            ("Bibliothek", os.path.join("Tray", "0x00000000!0x0000000000abcdef.householdbinary"))})
        self.assertEqual([n for n, _r in result["uebersprungen"]], [os.path.join("Set", "Schon_da.package")])
        self.assertEqual([n for n, _r in result["fehler"]], [os.path.join("Set", "kaputt.package")])
        # zweimal installieren legt nichts doppelt an
        again = downloads.install(self.archive, self.mods, self.tray)
        self.assertEqual(again["installiert"], [])
        self.assertEqual(len(again["uebersprungen"]), 6)

    def test_web_page_instead_of_file(self):
        from simvault.web import downloads
        page = os.path.join(self.tmp, "datei.package")
        with open(page, "w") as f:
            f.write("<!DOCTYPE html><html>Login</html>")
        result = downloads.install(page, self.mods, self.tray)
        self.assertIn("beschädigt", result["fehler"][0][1])
        html = os.path.join(self.tmp, "seite.htm")
        with open(html, "w") as f:
            f.write("<html>Login</html>")
        self.assertIn("Webseite", downloads.install(html, self.mods, self.tray)["fehler"][0][1])

    @unittest.skipUnless(HAVE_CRYPTO, "cryptography nicht installiert")
    def test_download_with_cookies_and_login_page(self):
        from simvault.web import secure_store
        from simvault.web import web_session
        with open(self.archive, "rb") as f:
            data = f.read()
        server, base = start_server({"/dl/12345": (data, "application/zip",
                                                    'attachment; filename="Kijiko Set.zip"')})
        try:
            store = secure_store.SecureStore(os.path.join(self.tmp, "store"))
            store.save("test", [{"name": "sid", "value": "abc", "domain": "127.0.0.1", "path": "/"}])
            session = web_session.WebSession(store)
            folder = os.path.join(self.tmp, "Downloads")
            path = session.download(base + "/dl/12345", folder)
            self.assertEqual(os.path.basename(path), "Kijiko Set.zip")
            self.assertIn("sid=abc", _Handler.seen_cookies[-1])
            second = session.download(base + "/dl/12345", folder)          # nichts überschreiben
            self.assertEqual(os.path.basename(second), "Kijiko Set (2).zip")
            with self.assertRaises(web_session.NeedsBrowser):
                session.download(base + "/login-noetig", folder)
            self.assertEqual(sorted(os.listdir(folder)), ["Kijiko Set (2).zip", "Kijiko Set.zip"])   # keine Reste
        finally:
            server.shutdown()
            server.server_close()

    def test_cli_install_from_url(self):
        with open(self.archive, "rb") as f:
            data = f.read()
        server, base = start_server({"/Set.zip": (data, "application/zip", None)})
        sims = os.path.join(self.tmp, "Sims")
        os.makedirs(sims)
        shutil.move(self.mods, os.path.join(sims, "Mods"))
        shutil.move(self.tray, os.path.join(sims, "Tray"))
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"sims_folder": sims, "download_folder": os.path.join(self.tmp, "dl")}, f)
        try:
            self.assertEqual(main.main(["--config", cfg_path, "install", base + "/Set.zip"]), 0)
        finally:
            server.shutdown()
            server.server_close()
        self.assertTrue(os.path.isfile(os.path.join(sims, "Mods", "SimVault_heruntergeladen", "Set",
                                                    "Neues_Kleid.package")))


class WebSearchTests(unittest.TestCase):
    def test_full_source_results_with_images(self):
        from simvault.app import core
        from simvault.web.sources import loader as loader
        page = (b'<div class="r"><a href="/item/1">Kijiko Wimpern</a><img src="/img/1.jpg"><i>Kijiko</i></div>'
                b'<div class="r"><a href="/item/2">Kijiko Haare</a><img src="/img/2.jpg"><i>Kijiko</i></div>')
        server, base = start_server({"/suche": (page, "text/html", None),
                                     "/img/1.jpg": (b"\xff\xd8bild1", "image/jpeg", None),
                                     "/img/2.jpg": (b"\xff\xd8bild2", "image/jpeg", None)})
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, "testquelle.py"), "w", encoding="utf-8") as f:
                f.write(textwrap.dedent(f'''
                    import re
                    from simvault.web.sources.base import Source, SearchResult
                    class Test(Source):
                        id = "test"
                        name = "Testseite"
                        def search_url(self, q):
                            return "{base}/suche?q=" + q
                        def search(self, query, session=None):
                            html = session.render(self.search_url(query))
                            return [SearchResult(title=t, url="{base}" + u, image_url="{base}" + i, creator=c)
                                    for u, t, i, c in re.findall(
                                        r'<a href="([^"]+)">([^<]+)</a><img src="([^"]+)"><i>([^<]+)</i>', html)]
                    class Kaputt(Source):
                        id = "kaputt"
                        name = "Kaputte Seite"
                        def search(self, query, session=None):
                            raise OSError("Seite antwortet nicht")
                '''))
            from simvault.web.sources.builtin import builtin_sources
            off = {src.id: False for src in builtin_sources() if src.can_search}    # nur die Testquellen
            cfg = {"plugin_folders": [tmp], "sources_enabled": off}
            results, links, errors = core.web_search(cfg, "Kijiko", session=core.web_session(cfg))
            self.assertEqual([(r.title, r.creator, r.extra["bild"]) for r in results],
                             [("Kijiko Wimpern", "Kijiko", b"\xff\xd8bild1"),
                              ("Kijiko Haare", "Kijiko", b"\xff\xd8bild2")])
            self.assertEqual(results[0].extra["quelle"], "Testseite")
            self.assertEqual(errors, [("Kaputte Seite", "Seite antwortet nicht")])
            self.assertIn("Testseite", links)
            self.assertIn("Google", links)                                  # Link-Quellen weiter dabei
        finally:
            server.shutdown()
            server.server_close()
            shutil.rmtree(tmp)
            loader_cache = getattr(loader, "_cache", None)
            if isinstance(loader_cache, dict):
                loader_cache.clear()


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class BrowserTests(unittest.TestCase):
    def test_render_runs_javascript_and_keeps_cookies_in_memory(self):
        if sys.platform.startswith("linux"):
            os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        except ImportError:
            self.skipTest("Qt WebEngine nicht installiert")
        from simvault.web import secure_store
        from PySide6.QtCore import QTimer
        from simvault.gui.browser import BrowserCore
        page = b"<html><body><div id=x>vorher</div><script>document.getElementById('x').textContent='nachher-JS';" \
               b"document.cookie='probe=1; path=/'</script></body></html>"
        server, base = start_server({"/seite": (page, "text/html", None)})
        tmp = tempfile.mkdtemp()
        app = QApplication.instance() or QApplication([])
        try:
            browser = BrowserCore(secure_store.SecureStore(tmp), tmp)
            out = {}

            def worker():
                try:
                    out["html"] = browser.render(base + "/seite", timeout=40)
                except Exception as e:
                    out["error"] = e

            threading.Thread(target=worker, daemon=True).start()
            timer = QTimer()
            timer.timeout.connect(lambda: out and app.quit())
            timer.start(100)
            QTimer.singleShot(45000, app.quit)
            app.exec()
            timer.stop()
            self.assertIn("nachher-JS", out.get("html") or "", out.get("error"))
            self.assertEqual(browser.save_login("test", "127.0.0.1"), 1)
            self.assertEqual(secure_store.SecureStore(tmp).cookies("test")[0]["value"], "1")
            self.assertFalse([n for n in os.listdir(tmp) if n not in ("logins.bin", "logins.key")])  # nichts sonst
        finally:
            server.shutdown()
            server.server_close()
            shutil.rmtree(tmp, ignore_errors=True)


class DownloadGuardTests(unittest.TestCase):
    def test_newsea_third_download_within_5_minutes_is_held(self):
        from simvault.web.downloads import DownloadGuard, blocked_message
        now = [1000.0]
        guard = DownloadGuard(clock=lambda: now[0])
        url = "http://www.newseasims.com/downfile.php?proid=576&id=1426"
        self.assertEqual(guard.check(url)[0], 0)
        now[0] += 60
        self.assertEqual(guard.check("http://newseasims.com/downfile.php?proid=576&id=1426")[0], 0)  # gleiche Datei
        now[0] += 60
        wait, hint = guard.check(url)
        self.assertEqual(wait, 181)                       # bis die erste Anfrage 5 Minuten alt ist
        self.assertIn("1 Stunde", hint)
        self.assertIn("4 Min.", blocked_message(wait, hint))
        self.assertEqual(guard.check("http://www.newseasims.com/downfile.php?proid=576&id=1427")[0], 0)  # andere Datei
        self.assertEqual(guard.check("http://www.newseasims.com/inside-page.php?cid=1&id=576")[0], 0)   # keine Datei
        self.assertEqual(guard.check("https://www.thesimsresource.com/downloads/download/itemId/1")[0], 0)
        now[0] += 181
        self.assertEqual(guard.check(url)[0], 0)          # danach wieder erlaubt

    def test_web_session_respects_guard(self):
        import re
        from simvault.web import downloads
        from simvault.web.web_session import WebSession
        old = downloads.download_guard
        downloads.download_guard = downloads.DownloadGuard(limits=[(re.compile("example\\.org/file"), 0, 300, "Test")])
        try:
            with self.assertRaises(OSError) as ctx:
                WebSession().download("http://example.org/file?id=1", tempfile.gettempdir())
            self.assertIn("Nicht geladen: Test", str(ctx.exception))
        finally:
            downloads.download_guard = old

    def test_newsea_access_labels(self):
        from simvault.web.sources.sites import NewSea
        self.assertEqual(NewSea.access("Lipstick(Free)"), "Free – ohne Konto")
        self.assertEqual(NewSea.access("Hairstyle(Free2024)"), "Free – ohne Konto")
        self.assertEqual(NewSea.access("Hairstyle(Donate)plus"), "Donate – nur angemeldet")
        self.assertEqual(NewSea.access("Hairstyle(TopStuff)"), "TopStuff – nur angemeldet")
        self.assertEqual(NewSea.access("StarfoldSweet+"), "")


class CaptchaCheckTests(unittest.TestCase):
    CHALLENGE = "<html><head><title>Just a moment...</title></head><body>cf_chl_opt</body></html>"

    def test_is_challenge_ignores_normal_cloudflare_pages(self):
        from simvault.web.sources.base import is_challenge
        self.assertTrue(is_challenge(self.CHALLENGE))
        self.assertFalse(is_challenge('<html><script src="/cdn-cgi/challenge-platform/h/b/scripts/x.js"></script>'
                                      '<div class="result">Treffer</div></html>'))
        self.assertFalse(is_challenge(""))

    def test_fetch_raises_check_required_after_render(self):
        from simvault.web.sources.sites import fetch
        from simvault.web.sources.base import CheckRequired
        page = self.CHALLENGE

        class Session:
            renderer = object()
            renders = 0

            def get(self, url):
                return page

            def render(self, url):
                Session.renders += 1
                return page

        with self.assertRaises(CheckRequired) as ctx:
            fetch(Session(), "https://example.org/suche")
        self.assertEqual(ctx.exception.url, "https://example.org/suche")
        self.assertEqual(Session.renders, 2)            # einmal abwarten, ob sich die Prüfung selbst löst

        class Solved(Session):
            def render(self, url):
                return "<html>Treffer</html>"
        self.assertEqual(fetch(Solved(), "https://example.org/suche"), "<html>Treffer</html>")

    def test_web_search_reports_checks(self):
        from simvault.app import core
        from simvault.web.sources.base import CheckRequired, Source

        class Blocked(Source):
            id, name = "blocked", "Blockiert"

            def search_url(self, query):
                return "https://example.org/?q=" + query

            def search(self, query, session=None):
                raise CheckRequired("https://example.org/?q=" + query)

        class Fine(Source):
            id, name = "fine", "Gut"

            def search(self, query, session=None):
                from simvault.web.sources.base import SearchResult
                return [SearchResult(title="Haar", url="https://example.com/haar")]

        from simvault.web import sources
        old = sources.enabled_sources
        sources.enabled_sources = lambda cfg: [Blocked(), Fine()]
        try:
            checks = []
            results, links, errors = core.web_search({}, "haar", session=object(), with_images=False, checks=checks)
            self.assertEqual([r.title for r in results], ["Haar"])
            self.assertEqual(checks, [{"id": "blocked", "name": "Blockiert", "url": "https://example.org/?q=haar"}])
            self.assertIn("Prüfung nötig", errors[0][1])
            results, _l, _e = core.web_search({}, "haar", session=object(), with_images=False, only={"fine"})
            self.assertEqual([r.source_id for r in results], ["fine"])
        finally:
            sources.enabled_sources = old


if __name__ == "__main__":
    unittest.main()
