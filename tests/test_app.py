# Tests – Programm: Einrichtung, Backups, Updates, Datenbank, Sprachen, Ordnerstruktur, Programmfenster

from helpers import *  # noqa: F401,F403


class SetupTests(unittest.TestCase):
    def test_setup_saves_choices(self):
        from unittest import mock
        tmp = tempfile.mkdtemp()
        try:
            sims = os.path.join(tmp, "Die Sims 4")
            os.makedirs(sims)
            cfg_path = os.path.join(tmp, "config.json")
            answers = iter([sims, "-", "0", "n"])  # Sims-Ordner, kein Spielordner, kein Entpacker, keine Laufwerke
            with mock.patch("builtins.input", lambda _p: next(answers)):
                self.assertEqual(main.main(["--config", cfg_path, "setup"]), 0)
            with open(cfg_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual((saved["sims_folder"], saved["game_folder"], saved["extractor"], saved["search_drives"]),
                             (sims, "", "none", False))
        finally:
            shutil.rmtree(tmp)


class BackupRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mods = os.path.join(self.tmp, "Mods")
        self.backups = os.path.join(self.tmp, "backups")
        os.makedirs(os.path.join(self.mods, "CAS"))
        self._write("CAS/a.package", "A1")
        self._write("b.package", "B1")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write(self, rel, text):
        with open(os.path.join(self.mods, rel), "w") as f:
            f.write(text)

    def _read(self, rel):
        with open(os.path.join(self.mods, rel)) as f:
            return f.read()

    def _named(self, kind):
        from simvault.storage import backup_manager
        return [b["name"] for b in backup_manager.list_backups(self.backups) if b["art"] == kind]

    def test_full_restore_modes(self):
        from simvault.storage import backup_manager as bm
        name = os.path.basename(bm.full_zip_backup(self.mods, self.backups))
        self._write("b.package", "B2")                       # geändert
        os.remove(os.path.join(self.mods, "CAS", "a.package"))   # gelöscht
        self._write("neu.package", "N")                      # dazugekommen
        targets = {"mods": self.mods}
        out = bm.restore_backup(self.backups, name, targets, overwrite=False)
        self.assertEqual((out["wiederhergestellt"], out["uebersprungen"]), (1, 1))
        self.assertEqual((self._read("CAS/a.package"), self._read("b.package")), ("A1", "B2"))
        out = bm.restore_backup(self.backups, name, targets, overwrite=True, exact=True)
        self.assertEqual(self._read("b.package"), "B1")
        self.assertFalse(os.path.exists(os.path.join(self.mods, "neu.package")))
        self.assertTrue(os.path.isfile(os.path.join(out["beiseite"], "neu.package")))     # verschoben, nicht gelöscht

    def test_delta_restores_full_plus_deltas(self):
        import time
        from simvault.storage import backup_manager as bm
        bm.delta_backup(self.mods, self.backups)             # Ausgangsstand für die Hashes
        shutil.rmtree(os.path.join(self.backups, self._named("delta")[0]))
        os.makedirs(self.backups, exist_ok=True)
        full = bm.full_zip_backup(self.mods, self.backups)
        time.sleep(1.1)
        self._write("b.package", "B2")
        bm.delta_backup(self.mods, self.backups)
        time.sleep(1.1)
        self._write("c.package", "C3")
        last = os.path.basename(bm.delta_backup(self.mods, self.backups))
        for rel in ("b.package", "c.package", "CAS/a.package"):
            os.remove(os.path.join(self.mods, rel))
        out = bm.restore_backup(self.backups, last, {"mods": self.mods})
        self.assertEqual(out["kette"][0], os.path.basename(full))
        self.assertEqual(len(out["kette"]), 3)
        self.assertEqual((self._read("CAS/a.package"), self._read("b.package"), self._read("c.package")),
                         ("A1", "B2", "C3"))

    def test_zip_cannot_write_outside_target(self):
        import zipfile
        from simvault.storage import backup_manager as bm
        os.makedirs(self.backups)
        with zipfile.ZipFile(os.path.join(self.backups, "Mods_backup_20260101_000000.zip"), "w") as z:
            z.writestr("../draussen.txt", "x")
            z.writestr("ok.package", "y")
        out = bm.restore_backup(self.backups, "Mods_backup_20260101_000000.zip", {"mods": self.mods})
        self.assertEqual(out["wiederhergestellt"], 1)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "draussen.txt")))

    def test_cleanup_rules(self):
        import zipfile
        from datetime import datetime
        from simvault.storage import backup_manager as bm
        os.makedirs(self.backups)

        def full(stamp):
            with zipfile.ZipFile(os.path.join(self.backups, f"Mods_backup_{stamp}.zip"), "w") as z:
                z.writestr("a", "a")

        for stamp in ("20260101_100000", "20260601_100000", "20261101_100000", "20261110_100000"):
            full(stamp)
        os.makedirs(os.path.join(self.backups, "Mods_delta_20260105_100000"))    # hängt am Januar-Backup
        os.makedirs(os.path.join(self.backups, "Mods_delta_20261112_100000"))
        open(os.path.join(self.backups, "notizen.txt"), "w").close()             # fremde Datei bleibt unberührt
        now = datetime(2026, 11, 14)
        doomed = {b["name"] for b in bm.plan_cleanup(self.backups, keep_last=10, max_age_days=30, now=now)}
        self.assertEqual(doomed, {"Mods_backup_20260101_100000.zip", "Mods_backup_20260601_100000.zip",
                                  "Mods_delta_20260105_100000"})
        doomed = {b["name"] for b in bm.plan_cleanup(self.backups, keep_last=1, max_age_days=0, now=now)}
        self.assertNotIn("Mods_backup_20261110_100000.zip", doomed)              # das neueste bleibt immer
        self.assertIn("Mods_backup_20261101_100000.zip", doomed)
        removed, _freed = bm.cleanup_backups(self.backups, keep_last=1, max_age_days=0)
        self.assertEqual(sorted(os.listdir(self.backups)),
                         ["Mods_backup_20261110_100000.zip", "Mods_delta_20261112_100000", "notizen.txt"])
        self.assertEqual(len(removed), 4)


class UpdaterTests(unittest.TestCase):
    def test_version_compare(self):
        from simvault.app import updater
        self.assertTrue(updater.is_newer("v0.6.1", "0.6.0"))
        self.assertTrue(updater.is_newer("1.0", "0.9.9"))
        self.assertFalse(updater.is_newer("v0.6.0", "0.6.0"))
        self.assertFalse(updater.is_newer("v0.6", "0.6.0"))
        self.assertFalse(updater.is_newer("v0.5.9", "0.6.0"))
        self.assertFalse(updater.is_newer("", "0.6.0"))

    def test_check_download_and_swap_script(self):
        import io
        import zipfile
        from simvault.app import updater
        tmp = tempfile.mkdtemp()
        try:
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as z:
                z.writestr("SimVault/SimVault.exe", "exe")
                z.writestr("SimVault/_internal/lib.dll", "dll")
            data = payload.getvalue()
            release = {"tag_name": "v99.0.0", "body": "### Neu\n- alles", "html_url": "https://example.invalid/r",
                       "assets": [{"name": "SimVault-Windows.zip", "browser_download_url": "https://example.invalid/z",
                                   "size": len(data)}]}
            info = updater.check(fetch=lambda: release)
            self.assertTrue(info["neuer"])
            self.assertEqual((info["neueste"], info["groesse"]), ("99.0.0", len(data)))

            class Response(io.BytesIO):
                headers = {"Content-Length": str(len(data))}

            original = updater._get
            updater._get = lambda url, timeout: Response(data)
            try:
                path = updater.download(info, os.path.join(tmp, "updates"))
                self.assertTrue(zipfile.is_zipfile(path))
                updater._get = lambda url, timeout: Response(data[:50])       # abgebrochener Download
                with self.assertRaises(OSError):
                    updater.download(info, os.path.join(tmp, "updates2"))
                self.assertEqual(os.listdir(os.path.join(tmp, "updates2")), [])
            finally:
                updater._get = original
            new_dir = updater.extract(path, os.path.join(tmp, "entpackt"))
            self.assertTrue(os.path.isfile(os.path.join(new_dir, "SimVault.exe")))
            script = updater.write_swap_script(new_dir, r"C:\Programme\SimVault", 4711, os.path.join(tmp, "u.bat"))
            with open(script, encoding="utf-8") as f:
                text = f.read()
            self.assertIn('PID eq 4711', text)
            self.assertIn(f'robocopy "{new_dir}" "C:\\Programme\\SimVault" /E', text)
            self.assertFalse(updater.can_self_update())          # aus dem Quellcode gestartet: kein Selbst-Update
        finally:
            shutil.rmtree(tmp)


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class GuiSmokeTests(unittest.TestCase):
    def test_window_and_pages_with_data(self):
        from simvault.app import core
        from simvault.gui import theme
        from simvault.gui.main_window import MainWindow
        app = QApplication.instance() or QApplication([])
        theme.apply(app)
        tmp = tempfile.mkdtemp()
        try:
            sims = build_sims_folder(tmp)
            cfg_path = os.path.join(tmp, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"sims_folder": sims, "search_drives": False}, f)
            window = MainWindow(cfg_path)
            analysis = core.analyze(window.state.cfg)
            window.state.set_analysis(analysis)
            window.state.set_found({"dateien": [], "ordner": [], "nicht_lesbar": [], "gefunden": 0, "gesucht": 1})
            for i, (name, page) in enumerate(window.pages):
                window.nav.setCurrentRow(i)
                app.processEvents()
                self.assertIs(window.stack.currentWidget(), page)
            mods = dict(window.pages)["Mods"]
            self.assertEqual(mods.model.rowCount(), len(analysis["usage"]))
            missing = dict(window.pages)["Fehlende CC"]
            self.assertEqual(missing.model.rowCount(), len(analysis["missing"]["teile"]))
            conflicts = dict(window.pages)["Konflikte"]
            self.assertEqual(conflicts.model.rowCount(), len(analysis["conflicts"]["konflikte"]))
            self.assertGreater(conflicts.model.rowCount(), 0)
            repair_page = dict(window.pages)["Reparatur"]
            repair_page._checked(core.check_health(window.state.cfg, deep=True), True)
            self.assertGreater(repair_page.proxy.rowCount(), 0)          # Kaputt.package, Leer.package …
            backup_page = dict(window.pages)["Backup"]
            core.backup(window.state.cfg, "saves", "full")
            backup_page.refresh()
            self.assertEqual(backup_page.model.rowCount(), 1)
            # Custom Branding: eigener Name erscheint in Fenster und Seitenleiste
            raw = dict(window.state.raw, branding={"app_name": "MeinVault", "logo_path": ""})
            window.state.save_config(raw)
            self.assertEqual(window.title.text(), "MeinVault")
            self.assertTrue(window.windowTitle().startswith("MeinVault"))
            # Relative Ordner liegen neben der config.json
            self.assertEqual(window.state.cfg["report_folder"], os.path.join(tmp, "reports"))
            window.close()
        finally:
            shutil.rmtree(tmp)


class DatabaseTests(unittest.TestCase):
    def _data(self):
        from datetime import datetime
        summary = {"mods_ordner": "C:/Mods", "spielstaende": ["Slot_1.save"]}
        rows = [{"datei": "a.package", "kategorie": "CAS", "status": "genutzt", "spielstaende": ["Slot_1.save"],
                 "tray_eintraege": 0, "groesse_bytes": 10, "ressourcen": 2}]
        issues = [{"schwere": "Hinweis", "art": "Konflikt", "meldung": "x", "dateien": ["a", "b"]}]
        missing = [{"id": "0xAB", "art": "Haare", "anzahl": 3, "verwendet_von": ["Bella"], "quellen": ["Slot_1"]}]
        return datetime(2026, 11, 14, 12, 0), summary, issues, rows, missing

    def test_sqlite(self):
        from simvault.storage import database
        tmp = tempfile.mkdtemp()
        try:
            db = {"type": "sqlite", "sqlite_path": os.path.join(tmp, "sub", "s.db")}
            self.assertEqual(database.write_scan(db, *self._data()), 1)
            self.assertEqual(database.write_scan(db, *self._data()), 2)
            conn = sqlite3.connect(db["sqlite_path"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mod_files").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT used_by FROM missing_cc").fetchone()[0], '["Bella"]')
            conn.close()
            self.assertTrue(database.test_connection(db)[0])
        finally:
            shutil.rmtree(tmp)

    def _fake_driver(self, module_name, rows_returned=(7,)):
        import types
        log = []

        class Cursor:
            lastrowid = 5

            def execute(self, sql, params=None):
                log.append(("execute", sql, params))

            def executemany(self, sql, rows):
                log.append(("executemany", sql, list(rows)))

            def fetchone(self):
                return rows_returned

        class Conn:
            def cursor(self):
                return Cursor()

            def commit(self):
                log.append(("commit",))

            def rollback(self):
                log.append(("rollback",))

            def close(self):
                log.append(("close",))

        mod = types.ModuleType(module_name)
        mod.connect = lambda **kw: (log.append(("connect", kw)), Conn())[1]
        return mod, log

    def test_mysql_and_postgresql_sql(self):
        from simvault.storage import database
        for kind, module, port, scan_id, marker in (("mysql", "pymysql", 3306, 5, "AUTO_INCREMENT"),
                                                     ("postgresql", "psycopg", 5432, 7, "SERIAL")):
            fake, log = self._fake_driver(module)
            old = sys.modules.get(module)
            sys.modules[module] = fake
            os.environ["SIMVAULT_DB_PASSWORD"] = "geheim"
            try:
                db = {"type": kind, kind: {"user": "sim", "database": "sv"}}
                self.assertEqual(database.write_scan(db, *self._data()), scan_id)
            finally:
                del os.environ["SIMVAULT_DB_PASSWORD"]
                if old is None:
                    del sys.modules[module]
                else:
                    sys.modules[module] = old
            connect = log[0][1]
            self.assertEqual((connect["port"], connect["password"]), (port, "geheim"))
            sql = [entry[1] for entry in log if entry[0] in ("execute", "executemany")]
            self.assertTrue(any(marker in s for s in sql))
            inserts = [s for s in sql if s.startswith("INSERT")]
            self.assertTrue(all("%s" in s and "?" not in s for s in inserts))
            self.assertEqual("RETURNING id" in inserts[0], kind == "postgresql")
            self.assertEqual(log[-2:], [("commit",), ("close",)])

    def test_missing_driver_message(self):
        from simvault.storage import database
        import builtins
        real = builtins.__import__

        def no_driver(name, *a, **k):
            if name in ("pymysql", "mysql.connector", "mysql"):
                raise ImportError(name)
            return real(name, *a, **k)

        builtins.__import__ = no_driver
        try:
            ok, message = database.test_connection({"type": "mysql"})
        finally:
            builtins.__import__ = real
        self.assertFalse(ok)
        self.assertIn("pip install pymysql", message)


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        from simvault.app import i18n
        i18n.set_language("de")

    def test_tr_exact_patterns_and_german_default(self):
        from simvault.app import i18n
        i18n.set_language("de")
        self.assertEqual(i18n.tr("genutzt"), "genutzt")
        i18n.set_language("en")
        self.assertEqual(i18n.tr("genutzt"), "used")
        self.assertEqual(i18n.tr("Aufräumen (3)"), "Clean up (3)")
        self.assertEqual(i18n.tr("installiert: 2× Paket; 1 übersprungen"), "installed: 2× package; 1 skipped")
        self.assertEqual(i18n.tr("Unbekannter Satz"), "Unbekannter Satz")
        self.assertEqual(i18n.set_language("xx"), "de")

    def test_catalog_has_no_placeholder_mismatch(self):
        from simvault.app import i18n
        for src, dst in i18n.EN.items():
            self.assertEqual(src.count("{}"), dst.count("{}"), src)

    @unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
    def test_translate_widget_once(self):
        from simvault.app import i18n
        from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget
        QApplication.instance() or QApplication([])
        i18n.set_language("en")
        root = QWidget()
        lay = QVBoxLayout(root)
        button = QPushButton("Speichern")
        label = QLabel("Aufräumen (2)")
        lay.addWidget(button)
        lay.addWidget(label)
        i18n.translate_widget(root)
        self.assertEqual((button.text(), label.text()), ("Save", "Clean up (2)"))
        label.setText("Aufräumen (5)")                  # nachträglich gesetzter Text
        i18n.translate_widget(root)
        i18n.translate_widget(root)
        self.assertEqual(label.text(), "Clean up (5)")


class LanguageTests(unittest.TestCase):
    def tearDown(self):
        from simvault.app import i18n
        i18n.set_language("de")

    def test_every_cli_and_report_text_has_an_english_translation(self):
        import ast
        from simvault.app import i18n
        root = os.path.join(os.path.dirname(__file__), "..")
        for name in ("main.py", os.path.join("simvault", "storage", "report_generator.py")):
            with open(os.path.join(root, name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t":
                    arg = node.args[0]
                    values = [arg] if isinstance(arg, ast.Constant) else \
                        [x for x in (getattr(arg, "body", None), getattr(arg, "orelse", None)) if isinstance(x, ast.Constant)]
                    for v in values:
                        self.assertIn(v.value, i18n.EN, f"{name}: keine Übersetzung für {v.value!r}")

    def test_cli_speaks_english(self):
        import io
        import contextlib
        tmp = tempfile.mkdtemp()
        try:
            cfg = os.path.join(tmp, "config.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"sims_folder": tmp}, f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main.main(["--config", cfg, "--lang", "en", "config"])
            self.assertIn("Config file:", out.getvalue())
            self.assertIn("missing", out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main.main(["--config", cfg, "--lang", "de", "config"])
            self.assertIn("Konfigurationsdatei:", out.getvalue())
            args = main.build_parser().parse_args(["conflicts", "--clean"])
            self.assertTrue(args.aufraeumen)                  # englische Option, gleiche Wirkung
            args = main.build_parser().parse_args(["restore", "--skip", "Whims", "--no-backup"])
            self.assertEqual((args.ohne, args.ohne_backup), (["Whims"], True))
        finally:
            shutil.rmtree(tmp)

    def test_report_in_english(self):
        from simvault.app import i18n
        from simvault.storage.report_generator import generate_report
        tmp = tempfile.mkdtemp()
        try:
            mods = os.path.join(tmp, "Mods")
            os.makedirs(mods)
            open(os.path.join(mods, "leer.package"), "wb").close()
            scan = mod_folder_scanner.scan_mods_folder(mods)
            i18n.set_language("en")
            files = generate_report(scan, output_dir=os.path.join(tmp, "r"), formats=("html", "md", "json"))
            html = open([f for f in files if f.endswith(".html")][0], encoding="utf-8").read()
            md = open([f for f in files if f.endswith(".md")][0], encoding="utf-8").read()
            data = json.load(open([f for f in files if f.endswith(".json")][0], encoding="utf-8"))
            self.assertIn("<h2>Problems</h2>", html)
            self.assertIn("These files are 0 bytes.", md)
            self.assertIn("lang='en'", html)
            self.assertEqual(data["probleme"][0]["art"], "Leer")       # JSON bleibt deutsch (wird wieder eingelesen)
        finally:
            shutil.rmtree(tmp)


class LayoutTests(unittest.TestCase):
    def test_old_plugin_imports_still_work(self):
        # Erweiterungen schreiben „from sources.base import Source“ – das muss dieselbe Klasse liefern
        import sources.base
        from simvault.web.sources import base
        self.assertIs(sources.base, base)
        self.assertIs(sources.base.Source, base.Source)

    def test_project_dir_is_repository_root(self):
        from simvault import project_dir
        self.assertTrue(os.path.exists(os.path.join(project_dir(), "main.py")))
        self.assertTrue(os.path.isdir(os.path.join(project_dir(), "plugins")))


if __name__ == "__main__":
    unittest.main()
