# Tests – CC auf dem PC finden: Suche, Archive, Zurückholen, Spielordner

from helpers import *  # noqa: F401,F403


class SearchTests(unittest.TestCase):
    def test_query_from_filename(self):
        self.assertEqual(cc_searcher.query_from_filename("[Creator] Cool_Hair-v2 (Merged).package"), "Creator Cool Hair v2")
        self.assertIn("Cool+Hair", cc_searcher.search_links("Cool_Hair.package")["CurseForge"])


class FinderTests(unittest.TestCase):
    def test_find_and_restore(self):
        tmp = tempfile.mkdtemp()
        try:
            sims = os.path.join(tmp, "Electronic Arts", "Die Sims 4")
            mods = os.path.join(sims, "Mods")
            os.makedirs(mods)
            os.makedirs(os.path.join(sims, "saves"))
            dbpf.write_package(os.path.join(mods, "Installiert.package"), [(dbpf.TYPE_CASP, 0, CAS_ID, b"x")])
            build_real_layout_save(os.path.join(sims, "saves", "Slot_00000001.save"))

            fund = os.path.join(tmp, "Downloads")
            os.makedirs(os.path.join(fund, "alt"))
            dbpf.write_package(os.path.join(fund, "alt", "Haare_von_Ivka.package"),
                               [(dbpf.TYPE_CASP, 0, MISSING_CAS, b"hair"), (dbpf.TYPE_CASP, 0, 0x1111111111111111, b"")])
            dbpf.write_package(os.path.join(fund, "Nichts.package"), [(dbpf.TYPE_CASP, 0, 0x2222222222222222, b"")])
            inner = os.path.join(tmp, "inner.package")
            dbpf.write_package(inner, [(dbpf.TYPE_OBJD, 0, MISSING_OBJ, b"sofa")])
            with _zipfile.ZipFile(os.path.join(fund, "Moebel.zip"), "w") as z:
                z.write(inner, "Moebel/Sofa.package")
            with open(os.path.join(fund, "Paket.rar"), "wb") as f:
                f.write(b"Rar!\x1a\x07\x00 kaputt" * 10)

            cfg_path = os.path.join(tmp, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"sims_folder": sims, "report_folder": os.path.join(tmp, "reports"),
                           "database": {"sqlite_path": os.path.join(tmp, "db.sqlite")}}, f)
            self.assertEqual(main.main(["--config", cfg_path, "find", fund, "--restore"]), 0)

            restored = sorted(os.listdir(os.path.join(mods, cc_finder.RESTORE_SUBFOLDER)))
            self.assertEqual(restored, ["Haare_von_Ivka.package", "Sofa.package"])
            self.assertEqual(dbpf.read_index(os.path.join(mods, cc_finder.RESTORE_SUBFOLDER, "Sofa.package"))[0].instance,
                             MISSING_OBJ)

            report = [r for r in os.listdir(os.path.join(tmp, "reports")) if r.endswith(".json")][0]
            with open(os.path.join(tmp, "reports", report), encoding="utf-8") as f:
                data = json.load(f)
            fs = data["fundstellen"]
            self.assertEqual((fs["gefunden"], fs["gesucht"]), (2, 3))  # OBJ_ID ist hier nicht installiert
            self.assertEqual(sorted(d["datei"] for d in fs["dateien"]), ["Haare_von_Ivka.package", "Sofa.package"])
            self.assertEqual([u["pfad"] for u in fs["nicht_lesbar"]], [os.path.join(fund, "Paket.rar")])

            # gleiche Datei an zwei Orten wird zusammengefasst; --ohne lässt Funde aus
            os.makedirs(os.path.join(fund, "kopie"))
            shutil.copy(os.path.join(fund, "alt", "Haare_von_Ivka.package"), os.path.join(fund, "kopie"))
            parts = [{"id": f"0x{MISSING_CAS:016X}", "art": "Haare (Steckplatz 2)", "verwendet_von": ["Bella Grusel"]}]
            hits, _ = cc_finder.search([fund], {MISSING_CAS})
            grouped, n = cc_finder.summarize(hits, parts)
            self.assertEqual((len(grouped), n, len(grouped[0]["weitere_fundorte"])), (1, 1, 1))
            self.assertEqual(grouped[0]["verwendet_von"], ["Bella Grusel"])
            other = os.path.join(tmp, "Mods2")
            os.makedirs(other)
            self.assertEqual(cc_finder.restore(grouped, other, exclude=["ivka"]), ([], []))

            # erneutes Zurückholen überschreibt nichts
            self.assertEqual(cc_finder.restore([{"datei": "Sofa.package", "pfad": "egal", "archiv_eintrag": None}],
                                               mods), ([], []))
        finally:
            shutil.rmtree(tmp)


class SearchLocationTests(unittest.TestCase):
    def test_locations_and_system_dirs(self):
        tmp = tempfile.mkdtemp()
        try:
            a = os.path.join(tmp, "A")
            os.makedirs(os.path.join(a, "Unterordner"))
            os.makedirs(os.path.join(a, "Windows"))
            dbpf.write_package(os.path.join(a, "Windows", "x.package"), [(dbpf.TYPE_CASP, 0, MISSING_CAS, b"")])
            # verschachtelte Ordner werden nur einmal durchsucht, fehlende ignoriert
            locs = cc_finder.search_locations({}, [a, os.path.join(a, "Unterordner"), os.path.join(tmp, "fehlt")],
                                              drives=False)
            self.assertEqual(locs, [a])
            # Systemordner (hier "Windows") werden übersprungen
            hits, _ = cc_finder.search(locs, {MISSING_CAS})
            self.assertEqual(hits, [])
            if os.name != "nt":
                self.assertEqual(cc_finder.list_drives(), [])
        finally:
            shutil.rmtree(tmp)


@unittest.skipUnless(shutil.which("7z"), "7-Zip nicht installiert")
class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        os.makedirs(os.path.join(self.src, "Mods", "Haare"))
        dbpf.write_package(os.path.join(self.src, "Mods", "Haare", "Ivka_Hair.package"),
                           [(dbpf.TYPE_CASP, 0, MISSING_CAS, b"hair")])
        inner = os.path.join(self.tmp, "inner.package")
        dbpf.write_package(inner, [(dbpf.TYPE_OBJD, 0, MISSING_OBJ, b"sofa")])
        with _zipfile.ZipFile(os.path.join(self.src, "Moebel.zip"), "w") as z:
            z.write(inner, "Sofa.package")
        with open(os.path.join(self.src, "riesig.bin"), "wb") as f:
            f.write(b"x" * 1000)  # irrelevant, darf nicht entpackt werden
        self.fund = os.path.join(self.tmp, "fund")
        os.makedirs(self.fund)
        self.archive = os.path.join(self.fund, "Sim_mit_CC.7z")
        subprocess.run(["7z", "a", "-bd", self.archive, "."], cwd=self.src, capture_output=True, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _search(self, tools, keep_hits=True):
        work = os.path.join(self.tmp, "work")
        os.makedirs(work, exist_ok=True)
        return cc_finder.search([self.fund], {MISSING_CAS, MISSING_OBJ}, work_dir=work, tools=tools,
                                keep_hits=keep_hits), work

    def check_tool(self, tools):
        (hits, unreadable), work = self._search(tools)
        self.assertEqual(unreadable, [])
        by_entry = {h["archiv_eintrag"].replace("\\", "/"): h for h in hits}
        self.assertEqual(set(by_entry), {"Mods/Haare/Ivka_Hair.package", "Moebel.zip → Sofa.package"})
        self.assertTrue(all(h["pfad"] == self.archive for h in hits))
        # im Temp-Ordner liegen danach nur noch die beiden Funde – nichts sonst
        extracted = sorted(f for _r, _d, fs in os.walk(work) for f in fs)
        self.assertEqual(extracted, ["Ivka_Hair.package", "Sofa.package"])
        # Zurückholen aus dem Temp-Ordner
        parts = [{"id": f"0x{MISSING_CAS:016X}", "art": "Haare (Steckplatz 2)", "verwendet_von": []},
                 {"id": f"0x{MISSING_OBJ:016X}", "art": "Objekt", "verwendet_von": []}]
        found, n = cc_finder.summarize(hits, parts)
        mods = os.path.join(self.tmp, "Mods")
        created, failed = cc_finder.restore(found, mods)
        self.assertEqual(failed, [])
        self.assertEqual(sorted(os.path.basename(c) for c in created), ["Ivka_Hair.package", "Sofa.package"])

    def test_7zip(self):
        self.check_tool([("7z", shutil.which("7z"))])

    @unittest.skipUnless(shutil.which("bsdtar"), "bsdtar nicht installiert")
    def test_bsdtar(self):
        self.check_tool([("bsdtar", shutil.which("bsdtar"))])

    def test_without_restore_temp_stays_empty(self):
        (hits, _), work = self._search([("7z", shutil.which("7z"))], keep_hits=False)
        self.assertEqual(len(hits), 2)
        self.assertEqual([f for _r, _d, fs in os.walk(work) for f in fs], [])   # nichts liegen geblieben
        self.assertEqual(os.listdir(work), [])

    def test_low_disk_space_skips_archive(self):
        from unittest import mock
        with mock.patch.object(cc_finder, "FREE_SPACE_RESERVE", 10 ** 18):
            (hits, unreadable), work = self._search([("7z", shutil.which("7z"))])
        self.assertEqual(hits, [])
        self.assertIn("Speicherplatz", unreadable[0]["grund"])
        self.assertEqual(os.listdir(work), [])

    def test_stale_temp_cleanup(self):
        base = os.path.join(self.tmp, "tempbase")
        old = os.path.join(base, cc_finder.TEMP_PREFIX + "alt")
        new = os.path.join(base, cc_finder.TEMP_PREFIX + "neu")
        os.makedirs(old)
        os.makedirs(new)
        os.utime(old, (0, 0))
        self.assertEqual(cc_finder.cleanup_stale_temp(base), 1)
        self.assertEqual(os.listdir(base), [cc_finder.TEMP_PREFIX + "neu"])

    def test_restore_without_temp_reextracts(self):
        (hits, _), _work = self._search([("7z", shutil.which("7z"))], keep_hits=False)
        hits = [h for h in hits if "Ivka" in h["archiv_eintrag"]]
        found, _ = cc_finder.summarize(hits, [{"id": f"0x{MISSING_CAS:016X}", "art": "Haare", "verwendet_von": []}])
        created, _failed = cc_finder.restore(found, os.path.join(self.tmp, "Mods3"))
        self.assertEqual([os.path.basename(c) for c in created], ["Ivka_Hair.package"])

    def test_password_and_no_tool(self):
        locked = os.path.join(self.fund, "geschuetzt.7z")
        subprocess.run(["7z", "a", "-bd", "-pgeheim", "-mhe=on", locked, "Moebel.zip"], cwd=self.src,
                       capture_output=True, check=True)
        os.remove(self.archive)
        (hits, unreadable), _ = self._search([("7z", shutil.which("7z"))])
        self.assertEqual(hits, [])
        self.assertEqual(len(unreadable), 1)
        self.assertIn("Passwort", unreadable[0]["grund"])
        (hits, unreadable), _ = self._search([])
        self.assertIn("7-Zip installieren", unreadable[0]["grund"])

    def test_tool_choice_from_config(self):
        seven = shutil.which("7z")
        self.assertEqual(archive_tools.tools_from_config({"extractor": "none"}), [])
        self.assertEqual(archive_tools.tools_from_config({"extractor": seven})[0], ("7z", seven))
        self.assertEqual(archive_tools.tool_kind("C:/Programme/WinRAR/UnRAR.exe"), "unrar")


class ReasonAndHintTests(unittest.TestCase):
    def test_reasons(self):
        r = archive_tools._reason
        self.assertEqual(r("bsdtar", "tar.EXE: LZMA codec is unsupported\ntar.EXE: Error exit delayed"),
                         archive_tools.NEEDS_7ZIP)
        self.assertEqual(r("bsdtar", "tar.EXE: Encryption is not supported"), "mit Passwort geschützt")
        self.assertEqual(r("unrar", "", 11), "mit Passwort geschützt")
        self.assertEqual(r("bsdtar", "tar.EXE: Damaged 7-Zip archive"), "Archiv beschädigt oder unvollständig")
        self.assertEqual(r("7z", "irgendwas\nError exit delayed"), "irgendwas")

    def test_sims_hint(self):
        self.assertTrue(cc_finder.looks_like_sims(r"C:\Users\Hades\Downloads\MCAS Full Set - 05 June 2025.7z"))
        self.assertTrue(cc_finder.looks_like_sims(r"E:\Download\MTS_EgorBlagov_sims-mod-assistant-win32-x64.7z"))
        self.assertFalse(cc_finder.looks_like_sims(r"C:\Users\Hades\Downloads\ffmpeg-8.1.2-full_build.7z"))
        self.assertFalse(cc_finder.looks_like_sims(r"G:\Games\Forza Horizon 6\Content\media\stripped\stringtables\BR.zip"))


@unittest.skipUnless(shutil.which("7z"), "7-Zip nicht installiert")
class NestedRestoreTests(unittest.TestCase):
    def test_find_then_restore_from_report(self):
        tmp = tempfile.mkdtemp()
        try:
            sims = os.path.join(tmp, "Electronic Arts", "Die Sims 4")
            mods = os.path.join(sims, "Mods")
            os.makedirs(mods)
            os.makedirs(os.path.join(sims, "saves"))
            dbpf.write_package(os.path.join(mods, "Installiert.package"), [(dbpf.TYPE_CASP, 0, CAS_ID, b"x")])
            build_real_layout_save(os.path.join(sims, "saves", "Slot_00000001.save"))

            work = os.path.join(tmp, "bau")
            os.makedirs(work)
            hair = os.path.join(work, "Ivka_Hair.package")
            dbpf.write_package(hair, [(dbpf.TYPE_CASP, 0, MISSING_CAS, b"hair")])
            sofa = os.path.join(work, "Sofa.package")
            dbpf.write_package(sofa, [(dbpf.TYPE_OBJD, 0, MISSING_OBJ, b"sofa")])
            # inneres 7z mit den Haaren, inneres ZIP mit dem Sofa – beide in einem äußeren ZIP (wie 打包.zip)
            subprocess.run(["7z", "a", "-bd", os.path.join(work, "haushalt.7z"), "Ivka_Hair.package"],
                           cwd=work, capture_output=True, check=True)
            with _zipfile.ZipFile(os.path.join(work, "moebel.zip"), "w", _zipfile.ZIP_DEFLATED) as z:
                z.write(sofa, "Mods/所有mod/Sofa.package")
            fund = os.path.join(tmp, "D")
            os.makedirs(fund)
            with _zipfile.ZipFile(os.path.join(fund, "打包.zip"), "w") as z:
                z.write(os.path.join(work, "haushalt.7z"), "a/haushalt.7z")
                z.write(os.path.join(work, "moebel.zip"), "b/moebel.zip")
            # ein 7z, das fälschlich .zip heißt
            subprocess.run(["7z", "a", "-bd", "-t7z", os.path.join(fund, "falsch.zip"), "Ivka_Hair.package"],
                           cwd=work, capture_output=True, check=True)

            cfg_path = os.path.join(tmp, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"sims_folder": sims, "report_folder": os.path.join(tmp, "reports"),
                           "extractor": shutil.which("7z"), "search_drives": False,
                           "database": {"sqlite_path": os.path.join(tmp, "db.sqlite")}}, f)
            self.assertEqual(main.main(["--config", cfg_path, "find", fund]), 0)
            restore_dir = os.path.join(mods, cc_finder.RESTORE_SUBFOLDER)
            self.assertFalse(os.path.exists(restore_dir))  # find ohne --restore ändert nichts

            report = [r for r in os.listdir(os.path.join(tmp, "reports")) if r.endswith(".json")][0]
            with open(os.path.join(tmp, "reports", report), encoding="utf-8") as f:
                fs = json.load(f)["fundstellen"]
            locations = {d["datei"]: [f"{d['pfad']} → {d['archiv_eintrag']}"] + d["weitere_fundorte"]
                         for d in fs["dateien"]}
            self.assertEqual(sorted(locations), ["Ivka_Hair.package", "Sofa.package"])
            self.assertTrue(any(x.endswith("b/moebel.zip → Mods/所有mod/Sofa.package") for x in locations["Sofa.package"]))
            self.assertTrue(any("falsch.zip" in x for x in locations["Ivka_Hair.package"]))   # falsche Endung erkannt
            self.assertTrue(any("a/haushalt.7z → Ivka_Hair.package" in x for x in locations["Ivka_Hair.package"]))
            self.assertEqual(fs["nicht_lesbar"], [])

            backups = os.path.join(tmp, "backups")
            with open(cfg_path, encoding="utf-8") as f:
                cfg_data = json.load(f)
            cfg_data["backup_folder"] = backups
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f)
            self.assertEqual(main.main(["--config", cfg_path, "restore", "--ohne", "nichts-davon"]), 0)
            self.assertEqual(sorted(os.listdir(restore_dir)), ["Ivka_Hair.package", "Sofa.package"])
            # vorher wurde der Mods-Ordner gesichert – im Backup ist der Wiederherstellungsordner noch nicht drin
            (backup_zip,) = os.listdir(backups)
            with _zipfile.ZipFile(os.path.join(backups, backup_zip)) as z:
                self.assertEqual(z.namelist(), ["Installiert.package"])
            self.assertEqual(dbpf.read_index(os.path.join(restore_dir, "Sofa.package"))[0].instance, MISSING_OBJ)
            # Temp-Ordner aufgeräumt
            self.assertEqual([d for d in os.listdir(tempfile.gettempdir()) if d.startswith(cc_finder.TEMP_PREFIX)], [])
        finally:
            shutil.rmtree(tmp)


class RestoreFallbackTests(unittest.TestCase):
    def test_uses_next_location_if_first_fails(self):
        tmp = tempfile.mkdtemp()
        try:
            good = os.path.join(tmp, "gut.zip")
            pkg = os.path.join(tmp, "x.package")
            dbpf.write_package(pkg, [(dbpf.TYPE_CASP, 0, MISSING_CAS, b"")])
            with _zipfile.ZipFile(good, "w") as z:
                z.write(pkg, "Mods/x.package")
            item = {"datei": "x.package", "pfad": os.path.join(tmp, "weg.zip"), "archiv_eintrag": "Mods/x.package",
                    "weitere_fundorte": [f"{good} → Mods/x.package"]}
            created, failed = cc_finder.restore([item], os.path.join(tmp, "Mods"))
            self.assertEqual((len(created), failed), (1, []))
        finally:
            shutil.rmtree(tmp)


class RestorePlanTests(unittest.TestCase):
    def _item(self, name, ids, size):
        return {"datei": name, "pfad": "D:\\" + name, "archiv_eintrag": None,
                "ids": [hex(i) for i in ids], "groesse": size}

    def test_no_duplicates_and_installed_skipped(self):
        from simvault.finder.cc_finder import plan_restore
        a, b, c = 1 << 40, 2 << 40, 3 << 40
        found = [self._item("Set.package", [a, b], 900), self._item("Wimpern.package", [a], 100),
                 self._item("Schon_da.package", [c], 50)]
        chosen, skipped = plan_restore(found, installed_ids={c})
        self.assertEqual([i["datei"] for i in chosen], ["Set.package"])
        self.assertEqual({n for n, _r in skipped}, {"Wimpern.package", "Schon_da.package"})

    def test_smaller_file_wins_on_tie(self):
        from simvault.finder.cc_finder import plan_restore
        a = 1 << 40
        chosen, _ = plan_restore([self._item("Gross.package", [a], 900), self._item("Klein.package", [a], 10)])
        self.assertEqual([i["datei"] for i in chosen], ["Klein.package"])

    def test_sims_hint_not_too_broad(self):
        from simvault.finder.cc_finder import looks_like_sims
        self.assertFalse(looks_like_sims(r"F:\games\Mods und setups Mass effect\ALOV.7z"))
        self.assertFalse(looks_like_sims(r"E:\Download\Ocarina of time Patreon.rar"))
        self.assertTrue(looks_like_sims(r"C:\Downloads\MCAS Full Set.7z"))
        self.assertTrue(looks_like_sims(r"D:\Sims4 CC\Haare.zip"))


class GameLocatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _install(self, *parts, packs=()):
        path = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.join(path, "Data", "Client"))
        for pack in packs:
            os.makedirs(os.path.join(path, pack))
        return path

    def test_finds_installs_and_ignores_user_folder(self):
        from simvault.finder import game_locator
        common = self._install("Program Files", "EA Games", "The Sims 4", packs=("EP01", "GP02", "Game"))
        deep = self._install("Zocken", "EA", "Die Sims 4")
        os.makedirs(os.path.join(self.tmp, "Dokumente", "Die Sims 4", "Mods"))    # Benutzerordner: keine Installation
        quick = game_locator.find_game_folders(deep=False, roots=[self.tmp])
        self.assertEqual([(c["pfad"], c["packs"]) for c in quick], [(common, 2)])
        both = game_locator.find_game_folders(deep=True, roots=[self.tmp])
        self.assertEqual([c["pfad"] for c in both], [common, deep])

    def test_steam_library_file(self):
        from simvault.finder import game_locator
        steam = os.path.join(self.tmp, "Steam")
        lib = os.path.join(self.tmp, "Lib2")
        os.makedirs(os.path.join(steam, "steamapps"))
        game = self._install("Lib2", "steamapps", "common", "The Sims 4")
        with open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), "w", encoding="utf-8") as f:
            f.write('"libraryfolders"\n{\n "1"\n {\n  "path"\t\t"%s"\n }\n}\n' % lib.replace("\\", "\\\\"))
        found = [p for p, _src in game_locator._steam_candidates([steam]) if game_locator.is_game_folder(p)]
        self.assertEqual(found, [game])


    def test_registry_entries(self):
        """Registry-Suche mit nachgebauter Registry: EA-App-Eintrag und Eintrag in der Programmliste."""
        import types
        from simvault.finder import game_locator
        ea = self._install("EA", "The Sims 4", packs=("EP01",))
        steam = self._install("SteamLib", "The Sims 4")
        uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        registry = {
            ("HKLM", r"SOFTWARE\Maxis\The Sims 4"): {"Install Dir": ea},
            ("HKLM", uninstall): {},
            ("HKLM", uninstall + "\\Steam App 1222670"): {"DisplayName": "The Sims™ 4", "InstallLocation": steam},
            ("HKLM", uninstall + "\\{ABC}"): {"DisplayName": "7-Zip"},
        }

        class Key:
            def __init__(self, root, path):
                self.root, self.path = root, path

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def open_key(root, path, _reserved=0, _access=0):
            if (root, path) not in registry:
                raise OSError(path)
            return Key(root, path)

        def query_value(key, name):
            values = registry[(key.root, key.path)]
            if name not in values:
                raise OSError(name)
            return values[name], 1

        def subkeys(key):
            prefix = key.path + "\\"
            return [p[len(prefix):] for (r, p) in registry if r == key.root and p.startswith(prefix)]

        fake = types.SimpleNamespace(
            HKEY_LOCAL_MACHINE="HKLM", HKEY_CURRENT_USER="HKCU", KEY_READ=1, KEY_WOW64_64KEY=2, KEY_WOW64_32KEY=4,
            OpenKey=open_key, QueryValueEx=query_value,
            QueryInfoKey=lambda key: (len(subkeys(key)), 0, 0), EnumKey=lambda key, i: subkeys(key)[i])
        old = sys.modules.get("winreg")
        sys.modules["winreg"] = fake
        try:
            found = {os.path.normpath(p): src for p, src in game_locator._registry_candidates()}
        finally:
            if old is None:
                del sys.modules["winreg"]
            else:
                sys.modules["winreg"] = old
        self.assertEqual(found, {ea: "EA App / Origin (Registry)", steam: "Windows-Programmliste"})


if __name__ == "__main__":
    unittest.main()
