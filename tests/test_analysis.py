# Tests – Analyse: DBPF-Pakete, Spielstände, fehlende CC, Konflikte, Reparatur, Vorschaubilder, Grundstücke

from helpers import *  # noqa: F401,F403


class DBPFTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_roundtrip_with_zlib(self):
        path = os.path.join(self.tmp, "a.package")
        dbpf.write_package(path, [(dbpf.TYPE_CASP, 0x80000000, CAS_ID, b"hello"),
                                  (dbpf.TYPE_OBJD, 0, OBJ_ID, b"x" * 1000, True)])
        entries = dbpf.read_index(path)
        self.assertEqual([e.instance for e in entries], [CAS_ID, OBJ_ID])
        self.assertEqual(entries[1].compression, dbpf.COMPRESSION_ZLIB)
        self.assertEqual(dbpf.read_resource(path, entries[0]), b"hello")
        self.assertEqual(dbpf.read_resource(path, entries[1]), b"x" * 1000)

    def test_index_with_constant_type(self):
        # Index-Flags 0x1: Typ steht einmal im Index-Kopf statt in jedem Eintrag
        data = b"abc"
        index = struct.pack("<II", 0x1, dbpf.TYPE_CASP)
        index += struct.pack("<IIIIIIHH", 0, CAS_ID >> 32, CAS_ID & 0xFFFFFFFF, 96, len(data) | 0x80000000, len(data), 0, 1)
        header = bytearray(96)
        header[0:4] = b"DBPF"
        struct.pack_into("<II", header, 4, 2, 1)
        struct.pack_into("<I", header, 36, 1)
        struct.pack_into("<I", header, 44, len(index))
        struct.pack_into("<I", header, 64, 96 + len(data))
        path = os.path.join(self.tmp, "c.package")
        with open(path, "wb") as f:
            f.write(bytes(header) + data + index)
        (e,) = dbpf.read_index(path)
        self.assertEqual((e.type, e.instance), (dbpf.TYPE_CASP, CAS_ID))
        self.assertEqual(dbpf.read_resource(path, e), b"abc")

    def test_refpack_literals_and_copy(self):
        payload = bytes(range(256)) * 3 + b"xyz"
        self.assertEqual(dbpf.refpack_decompress(refpack_literals(payload)), payload)
        # "abcd" als Literal, dann 3 Bytes ab Abstand 4 kopieren -> "abcdabc"
        stream = bytes([0x10, 0xFB, 0, 0, 7, 0xE0]) + b"abcd" + bytes([0x00, 0x03, 0xFC])
        self.assertEqual(dbpf.refpack_decompress(stream), b"abcdabc")
        # überlappende Kopie: "ab" + 6 Bytes ab Abstand 2 -> "abababab"
        b0 = (0 << 5) | ((6 - 3) << 2) | 2  # plain=2, len=6, offset-1=1
        stream = bytes([0x10, 0xFB, 0, 0, 8, b0, 0x01]) + b"ab" + bytes([0xFC])
        self.assertEqual(dbpf.refpack_decompress(stream), b"abababab")

    def test_broken_package(self):
        path = os.path.join(self.tmp, "b.package")
        with open(path, "wb") as f:
            f.write(b"NOPE" + b"\0" * 200)
        with self.assertRaises(dbpf.DBPFError):
            dbpf.read_index(path)
        dbpf.write_package(path, [(dbpf.TYPE_CASP, 0, CAS_ID, b"z" * 100)])
        with open(path, "r+b") as f:  # abschneiden
            f.truncate(120)
        with self.assertRaises(dbpf.DBPFError):
            dbpf.read_index(path)


class ScanAndAnalyzeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.sims = build_sims_folder(cls.tmp)
        cls.mods = os.path.join(cls.sims, "Mods")
        cls.scan = mod_folder_scanner.scan_mods_folder(cls.mods)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _issue(self, kind):
        found = [i for i in self.scan.issues if i.kind == kind]
        self.assertTrue(found, f"Problem '{kind}' nicht gemeldet")
        return found

    def test_categories(self):
        cats = {os.path.basename(m.rel_path): m.category for m in self.scan.mods}
        self.assertEqual(cats["[Creator] Cool_Hair.package"], "CAS")
        self.assertEqual(cats["Sofa.package"], "Objekt")
        self.assertEqual(cats["Trait.package"], "Tuning/Sonstiges")
        self.assertEqual(cats["MeinScript.ts4script"], "Script")
        self.assertEqual(cats["Kaputt.package"], "Defekt")
        self.assertEqual(cats["Leer.package"], "Defekt")

    def test_issues(self):
        self.assertIn(os.path.join("a", "b", "c", "d", "e", "f", "ZuTief.package"), self._issue("Paket zu tief")[0].files)
        self.assertEqual(self._issue("Script zu tief")[0].files, [os.path.join("Scripts", "Zu", "Tief.ts4script")])
        self.assertTrue(any("Kaputt.package" in f for f in self._issue("Beschädigt")[0].files))
        self.assertEqual(self._issue("Leer")[0].files, ["Leer.package"])
        self.assertEqual(self._issue("Archiv")[0].files, ["Download.zip"])
        dup = sorted([os.path.join("CAS", "Kleid.package"), "Kleid Kopie.package"])
        self.assertIn(dup, [sorted(i.files) for i in self._issue("Duplikat")])
        conflicts = self._issue("Konflikt")
        self.assertTrue(any(os.path.join("Merged", "Merge (Merged).package") in c.files for c in conflicts))
        # die reine Duplikat-Kombination darf nicht zusätzlich als Konflikt auftauchen
        self.assertFalse(any(sorted(c.files) == sorted(dup) for c in conflicts))

    def test_usage(self):
        saves = savegame_analyzer.find_saves(os.path.join(self.sims, "saves"))
        self.assertEqual([os.path.basename(s) for s in saves], ["Slot_00000001.save"])
        rows = savegame_analyzer.analyze_usage(self.scan, saves, os.path.join(self.sims, "Tray"))
        status = {os.path.basename(r["mod"].rel_path): r for r in rows}
        self.assertEqual(status["[Creator] Cool_Hair.package"]["status"], "genutzt")
        self.assertEqual(status["[Creator] Cool_Hair.package"]["saves"], ["Slot_00000001.save"])
        self.assertEqual(status["Kleid.package"]["status"], "genutzt")
        self.assertEqual(status["Sofa.package"]["status"], "genutzt")          # fixed64 im Spielstand
        self.assertEqual(status["Trait.package"]["status"], "genutzt")         # Tuning-ID am Sim
        self.assertEqual(status["Ungenutzt.package"]["status"], "ungenutzt")
        self.assertEqual(status["AndererMod.package"]["status"], "nicht nachweisbar")
        self.assertEqual(status["MeinScript.ts4script"]["status"], "nicht prüfbar")
        self.assertEqual(status["Kaputt.package"]["status"], "defekt")
        tray = status["TrayCC.package"]
        self.assertEqual((tray["status"], tray["saves"], tray["tray"]), ("genutzt", [], 1))

    def test_refpack_resource_in_save(self):
        proto = make_savegame_proto([CAS_ID], [])
        path = os.path.join(self.tmp, "Slot_000000AA.save")
        dbpf.write_package(path, [(dbpf.TYPE_SAVEGAME_DATA, 0, 1, b"")])
        # Ressource nachträglich durch RefPack-Daten ersetzen
        packed = refpack_literals(proto)
        with open(path, "rb") as f:
            raw = bytearray(f.read())
        (e,) = dbpf.read_index(path)
        body = raw[:96] + packed
        index = struct.pack("<I", 0) + struct.pack("<IIIIIIIHH", e.type, 0, 0, 1, 96,
                                                  len(packed) | 0x80000000, len(proto), 0xFFFF, 1)
        header = bytearray(raw[:96])
        struct.pack_into("<I", header, 64, len(body))
        struct.pack_into("<I", header, 44, len(index))
        with open(path, "wb") as f:
            f.write(bytes(header) + bytes(body[96:]) + index)
        self.assertEqual(savegame_analyzer.ids_in_save(path, {CAS_ID, OBJ_ID}), {CAS_ID})


class EndToEndTests(unittest.TestCase):
    def test_cli_analyze_writes_reports(self):
        tmp = tempfile.mkdtemp()
        try:
            sims = build_sims_folder(tmp)
            cfg_path = os.path.join(tmp, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"sims_folder": sims,
                           "report_folder": os.path.join(tmp, "reports"),
                           "backup_folder": os.path.join(tmp, "backups"),
                           "database": {"sqlite_path": os.path.join(tmp, "db.sqlite")}}, f)
            self.assertEqual(main.main(["--config", cfg_path]), 0)
            reports = sorted(os.listdir(os.path.join(tmp, "reports")))
            self.assertEqual([os.path.splitext(r)[1] for r in reports], [".csv", ".html", ".json", ".md"])
            data = json.load(open(os.path.join(tmp, "reports", [r for r in reports if r.endswith(".json")][0]), encoding="utf-8"))
            self.assertEqual(data["zusammenfassung"]["status"]["ungenutzt"], 2)  # Ungenutzt, ZuTief (Merge enthält das genutzte Kleid)
            html = open(os.path.join(tmp, "reports", [r for r in reports if r.endswith(".html")][0]), encoding="utf-8").read()
            self.assertIn("[Creator] Cool_Hair.package", html)
            self.assertIn("thesimsresource.com/downloads/browse/category/sims4/search/Kaputt/", html)
            conn = sqlite3.connect(os.path.join(tmp, "db.sqlite"))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM mod_files").fetchone()[0], len(data["mods"]))
            conn.close()

            self.assertEqual(main.main(["--config", cfg_path, "backup", "saves", "--mode", "delta"]), 0)
            self.assertEqual(main.main(["--config", cfg_path, "backup", "mods"]), 0)
            backups = os.listdir(os.path.join(tmp, "backups"))
            self.assertTrue(any(b.startswith("saves_delta_") for b in backups))
            self.assertTrue(any(b.startswith("Mods_backup_") and b.endswith(".zip") for b in backups))
        finally:
            shutil.rmtree(tmp)


class MissingCCTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_save_and_tray(self):
        save = os.path.join(self.tmp, "Slot_00000001.save")
        build_real_layout_save(save)
        tray = os.path.join(self.tmp, "Tray")
        os.makedirs(tray)
        hh = f_bytes(1, f_bytes(6, sim_proto("Ahri", "KDA", [MISSING_TRAY_CAS, EA_CAS])))
        with open(os.path.join(tray, "0x00000000!0x05a40ce453830037.householdbinary"), "wb") as f:
            f.write(struct.pack("<II", 1, len(hh)) + hh)
        item = (f_varint(2, 1) + f_bytes(4, "K/DA Girls".encode())
                + f_bytes(5, "Hair by Ivka: https://ivkasims.tumblr.com/post/1 #kda".encode())
                + f_bytes(7, b"MeoPoMa") + f_varint(11, 63752705085))
        with open(os.path.join(tray, "0x00000001!0x05a40ce453830037.trayitem"), "wb") as f:
            f.write(struct.pack("<II", 0, len(item)) + item)

        known = {CAS_ID, OBJ_ID}
        result = missing_cc.find_missing([save], tray, known)
        rows = {r["id"]: r for r in result["teile"]}
        self.assertEqual(set(rows), {f"0x{MISSING_CAS:016X}", f"0x{MISSING_OBJ:016X}", f"0x{MISSING_TRAY_CAS:016X}"})

        cas = rows[f"0x{MISSING_CAS:016X}"]
        self.assertEqual((cas["art"], cas["anzahl"], cas["verwendet_von"]),
                         ("Haare (Steckplatz 2)", 2, ["Bella Grusel (2×)"]))
        self.assertEqual(cas["gruppen"], ["Slot_00000001.save"])
        obj = rows[f"0x{MISSING_OBJ:016X}"]
        self.assertEqual(obj["art"], "Objekt")
        self.assertEqual(sorted(obj["verwendet_von"]),
                         ["Grundstück Gut Eichhof", "Haushaltsinventar Grusel", "Inventar von Bella Grusel"])
        tray_row = rows[f"0x{MISSING_TRAY_CAS:016X}"]
        self.assertEqual(tray_row["verwendet_von"], ["Bibliothek „K/DA Girls“: Ahri KDA"])
        self.assertEqual(tray_row["art"], "CAS-Teil")  # ohne Steckplatz-Liste

        (hh,) = result["bibliothek"]
        self.assertEqual((hh["name"], hh["ersteller"], hh["typ"], hh["datum"]),
                         ("K/DA Girls", "MeoPoMa", "Haushalt", "2021-03-29"))
        self.assertEqual(hh["links"], ["https://ivkasims.tumblr.com/post/1"])
        self.assertEqual(hh["fehlend"], [{"id": f"0x{MISSING_TRAY_CAS:016X}", "art": "CAS-Teil"}])
        self.assertIn("MeoPoMa+K%2FDA+Girls", hh["suche"])
        self.assertEqual(tray_row["quellen"], ["Bibliothek"])

        # Mit Spiel-IDs: was zum Spiel gehört, ist nicht fehlend
        result = missing_cc.find_missing([save], None, known | {MISSING_CAS, MISSING_OBJ})
        self.assertEqual(result, {"teile": [], "bibliothek": []})

    def test_game_index_and_cache(self):
        game = os.path.join(self.tmp, "The Sims 4")
        os.makedirs(os.path.join(game, "Data", "Client"))
        dbpf.write_package(os.path.join(game, "Data", "Client", "ClientFullBuild0.package"),
                           [(dbpf.TYPE_CASP, 0, MISSING_CAS, b"x"), (dbpf.TYPE_CASP, 0, EA_CAS, b"y"),
                            (0x62E94D38, 0, 0xABCDEF0123456789, b"tuning")])
        cache = os.path.join(self.tmp, "cache.json")
        self.assertEqual(missing_cc.index_game_content(game, cache), {MISSING_CAS})
        self.assertTrue(os.path.exists(cache))
        self.assertEqual(missing_cc.index_game_content(game, cache), {MISSING_CAS})  # aus dem Cache

    def test_packed_fixed64_counts_as_used(self):
        save = os.path.join(self.tmp, "Slot_00000001.save")
        build_real_layout_save(save)
        self.assertIn(CAS_ID, savegame_analyzer.ids_in_save(save, {CAS_ID}))


class ConflictTests(unittest.TestCase):
    """Konflikte werden nach Art eingeordnet und mit der Nutzung abgewogen."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mods = os.path.join(self.tmp, "Mods")
        os.makedirs(os.path.join(self.mods, "SimVault_wiederhergestellt"))
        tex = 0x00B2D882
        a, b, c, d = (n << 40 for n in (1, 2, 3, 4))
        w = dbpf.write_package
        # Set enthält Wimpern komplett (identisch) -> Wimpern überflüssig
        w(os.path.join(self.mods, "Set.package"), [(dbpf.TYPE_CASP, 0, a, b"lash"), (tex, 0, a, b"tex" * 50, True),
                                                   (dbpf.TYPE_CASP, 0, b, b"brow")])
        w(os.path.join(self.mods, "Wimpern.package"), [(dbpf.TYPE_CASP, 0, a, b"lash"), (tex, 0, a, b"tex" * 50)])
        # zwei Varianten derselben Krone: gleiche ID, anderer Inhalt
        w(os.path.join(self.mods, "Ersel_Crown_Amnezia bigger.package"), [(dbpf.TYPE_CASP, 0, c, b"big")])
        w(os.path.join(self.mods, "Ersel_Crown_Amnezia smaller.package"), [(dbpf.TYPE_CASP, 0, c, b"small")])
        # Überschneidung: gleicher Inhalt, aber jede Datei hat Eigenes
        w(os.path.join(self.mods, "HaarA.package"), [(dbpf.TYPE_CASP, 0, d, b"hair"), (dbpf.TYPE_CASP, 0, 5 << 40, b"x")])
        w(os.path.join(self.mods, "HaarB.package"), [(dbpf.TYPE_CASP, 0, d, b"hair"), (dbpf.TYPE_CASP, 0, 6 << 40, b"y")])
        self.ids = (a, b, c, d)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _analyze(self, id_usage=None):
        from simvault.analysis import conflicts
        scan = mod_folder_scanner.scan_mods_folder(self.mods)
        return conflicts.analyze_conflicts(scan, id_usage)

    def test_kinds_and_recommendation(self):
        a, b, c, d = self.ids
        result = self._analyze({"saves": {c: ["Slot_00000001.save"]}, "tray": {}})
        by_kind = {k["art"]: k for k in result["konflikte"]}
        self.assertEqual(set(by_kind), {"Doppelt", "Konflikt", "Überschneidung"})
        self.assertEqual(by_kind["Doppelt"]["entfernbar"], ["Wimpern.package"])
        self.assertEqual([e["datei"] for e in result["entfernbar"]], ["Wimpern.package"])
        self.assertEqual(by_kind["Konflikt"]["unterschiedlich"], 1)
        self.assertEqual(by_kind["Konflikt"]["genutzt"], 1)
        self.assertEqual(by_kind["Konflikt"]["spielstaende"], ["Slot_00000001.save"])
        self.assertIn("Varianten", by_kind["Konflikt"]["empfehlung"])
        self.assertEqual(by_kind["Überschneidung"]["entfernbar"], [])
        self.assertEqual(result["konflikte"][0]["art"], "Konflikt")      # das Wichtigste zuerst

    def test_identical_twins_keep_one(self):
        # zwei inhaltsgleiche Pakete (verschieden gepackt): genau eines ist überflüssig, das zurückgeholte
        twin = [(dbpf.TYPE_CASP, 0, 9 << 40, b"same" * 30)]
        dbpf.write_package(os.path.join(self.mods, "Kleid.package"), twin)
        dbpf.write_package(os.path.join(self.mods, "SimVault_wiederhergestellt", "Kleid_neu.package"),
                           [twin[0] + (True,)])
        gone = [e["datei"] for e in self._analyze()["entfernbar"]]
        self.assertIn(os.path.join("SimVault_wiederhergestellt", "Kleid_neu.package"), gone)
        self.assertNotIn("Kleid.package", gone)

    def test_newer_version_wins_and_old_copies_are_stripped(self):
        from simvault.analysis import conflicts

        def casp(version, name, extra=b""):
            raw = name.encode("utf-16-be")
            return struct.pack("<III", version, 0, 0) + bytes([len(raw)]) + raw + extra

        lash, own = 20 << 40, 21 << 40
        dbpf.write_package(os.path.join(self.mods, "Lashes_v2.package"),
                           [(dbpf.TYPE_CASP, 0, lash, casp(40, "lash_bk", b"new")), (0x00B2D882, 0, lash, b"tex2")])
        old_set = os.path.join(self.mods, "SimVault_wiederhergestellt", "Altes_Set.package")
        dbpf.write_package(old_set, [(dbpf.TYPE_CASP, 0, lash, casp(30, "lash_bk")), (0x00B2D882, 0, lash, b"tex1"),
                                     (dbpf.TYPE_CASP, 0, own, casp(30, "brow_bk"))])
        result = self._analyze()
        conflict = next(c for c in result["konflikte"] if "Altes_Set.package" in c["namen"])
        self.assertEqual(conflict["art"], "Konflikt")
        self.assertIn("CAS-Format 40 statt 30", conflict["empfehlung"])
        self.assertEqual(conflict["loesung"]["aktion"], "bereinigen")
        self.assertEqual(conflict["loesung"]["behalten"], "Lashes_v2.package")
        out = conflicts.resolve(self.mods, result, self.tmp, os.path.join(self.tmp, "backups"))
        self.assertEqual(out["fehler"], [])
        self.assertEqual([e.instance for e in dbpf.read_index(old_set)], [own])       # nur das Eigene bleibt
        self.assertEqual(len(dbpf.read_index(os.path.join(out["backup"], "SimVault_wiederhergestellt",
                                                          "Altes_Set.package"))), 3)   # Original gesichert
        again = self._analyze()
        self.assertFalse([c for c in again["konflikte"] if "Altes_Set.package" in c["namen"]])
        self.assertEqual(again["aufloesbar"], [])

    def test_different_items_with_same_id_are_not_auto_resolved(self):
        def casp(version, name):
            raw = name.encode("utf-16-be")
            return struct.pack("<III", version, 0, 0) + bytes([len(raw)]) + raw

        dbpf.write_package(os.path.join(self.mods, "Rock.package"), [(dbpf.TYPE_CASP, 0, 30 << 40, casp(40, "rock"))])
        dbpf.write_package(os.path.join(self.mods, "Hose.package"), [(dbpf.TYPE_CASP, 0, 30 << 40, casp(30, "hose"))])
        result = self._analyze()
        conflict = next(c for c in result["konflikte"] if "Rock.package" in c["namen"])
        self.assertIn("verschiedene CC mit derselben ID", conflict["empfehlung"])
        self.assertIsNone(conflict["loesung"])

    def test_quarantine_moves_files_out(self):
        from simvault.analysis import conflicts
        result = self._analyze()
        target, moved, failed = conflicts.quarantine(self.mods, [e["datei"] for e in result["entfernbar"]], self.tmp)
        self.assertEqual((moved, failed), (["Wimpern.package"], []))
        self.assertFalse(os.path.exists(os.path.join(self.mods, "Wimpern.package")))
        self.assertTrue(os.path.isfile(os.path.join(target, "Wimpern.package")))
        self.assertEqual(self._analyze()["entfernbar"], [])


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mods = os.path.join(self.tmp, "Mods")
        self.saves = os.path.join(self.tmp, "saves")
        self.backups = os.path.join(self.tmp, "backups")
        os.makedirs(self.mods)
        os.makedirs(self.saves)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _check(self, deep=True):
        from simvault.analysis import repair
        return {it["datei"]: it for it in repair.check_all(self.mods, self.saves, deep=deep)}

    def test_diagnosis(self):
        dbpf.write_package(os.path.join(self.mods, "gut.package"), [(dbpf.TYPE_CASP, 0, CAS_ID, b"ok")])
        open(os.path.join(self.mods, "leer.package"), "wb").close()
        with open(os.path.join(self.mods, "seite.package"), "w") as f:
            f.write("<!DOCTYPE html><html>Please log in</html>")
        full = os.path.join(self.mods, "voll.package")
        dbpf.write_package(full, [(dbpf.TYPE_CASP, 0, CAS_ID_2, b"x" * 500)])
        with open(full, "rb") as f:
            data = f.read()
        with open(os.path.join(self.mods, "abgeschnitten.package"), "wb") as f:
            f.write(data[:300])
        items = self._check()
        self.assertEqual(items["gut.package"]["zustand"], "in Ordnung")
        self.assertEqual({n: items[n]["code"] for n in ("leer.package", "seite.package", "abgeschnitten.package")},
                         {"leer.package": "leer", "seite.package": "webseite",
                          "abgeschnitten.package": "abgeschnitten"})
        self.assertFalse(any(items[n]["reparierbar"] for n in ("leer.package", "seite.package",
                                                               "abgeschnitten.package")))

    def test_broken_resource_is_dropped_and_original_kept(self):
        from simvault.analysis import repair
        path = os.path.join(self.mods, "merge.package")
        dbpf.write_package(path, [(dbpf.TYPE_CASP, 0, CAS_ID, b"A" * 400, True),
                                  (dbpf.TYPE_CASP, 0, CAS_ID_2, b"B" * 400, True),
                                  (dbpf.TYPE_OBJD, 0, OBJ_ID, b"C" * 50)])
        entries = dbpf.read_index(path)
        with open(path, "r+b") as f:                 # zweite Ressource zerstören
            f.seek(entries[1].offset)
            f.write(b"\xff" * entries[1].file_size)
        self.assertEqual(self._check(deep=False)["merge.package"]["zustand"], "in Ordnung")   # nur gründlich sichtbar
        items = self._check(deep=True)
        self.assertEqual(items["merge.package"]["code"], "ressourcen")
        backup_dir, results = repair.repair_all(list(items.values()), self.backups, self.mods)
        self.assertEqual([(n, ok) for n, ok, _m in results], [("merge.package", True)])
        self.assertEqual([e.instance for e in dbpf.read_index(path)], [CAS_ID, OBJ_ID])
        self.assertEqual(dbpf.read_resource(path, dbpf.read_index(path)[0]), b"A" * 400)
        self.assertTrue(os.path.isfile(os.path.join(backup_dir, "Mods", "merge.package")))
        self.assertEqual(self._check(deep=True)["merge.package"]["zustand"], "in Ordnung")

    def test_misnamed_zip_is_unpacked(self):
        import zipfile
        from simvault.analysis import repair
        inner = os.path.join(self.tmp, "Echt.package")
        dbpf.write_package(inner, [(dbpf.TYPE_CASP, 0, CAS_ID, b"ok")])
        fake = os.path.join(self.mods, "Download.package")
        with zipfile.ZipFile(fake, "w") as z:
            z.write(inner, "Ordner/Echt.package")
        items = self._check()
        self.assertEqual(items["Download.package"]["code"], "archiv")
        _dir, results = repair.repair_all(list(items.values()), self.backups, self.mods)
        self.assertTrue(results[0][1], results)
        self.assertFalse(os.path.exists(fake))
        self.assertEqual(len(dbpf.read_index(os.path.join(self.mods, "Echt.package"))), 1)

    def test_save_restored_from_last_good_version(self):
        from simvault.analysis import repair
        good = [(dbpf.TYPE_SAVEGAME_DATA, 0, 1, make_savegame_proto([CAS_ID], []), True)]
        save = os.path.join(self.saves, "Slot_00000001.save")
        with open(save, "wb") as f:
            f.write(b"DBPF" + b"\0" * 40)             # kaputter Spielstand
        with open(save + ".ver0", "wb") as f:
            f.write(b"kaputt")                        # jüngste Sicherung ebenfalls kaputt
        dbpf.write_package(save + ".ver1", good)
        os.utime(save + ".ver1", (1_700_000_000, 1_700_000_000))
        dbpf.write_package(os.path.join(self.saves, "Slot_00000002.save"), good)
        items = self._check()
        self.assertEqual(items["Slot_00000002.save"]["zustand"], "in Ordnung")
        broken = items["Slot_00000001.save"]
        self.assertTrue(broken["reparierbar"])
        self.assertTrue(broken["ersatz"].endswith(".ver1"))
        backup_dir, results = repair.repair_all(list(items.values()), self.backups, self.mods)
        self.assertTrue(results[0][1], results)
        self.assertEqual(self._check()["Slot_00000001.save"]["zustand"], "in Ordnung")
        self.assertTrue(os.path.isfile(os.path.join(backup_dir, "saves", "Slot_00000001.save")))


class ThumbnailTests(unittest.TestCase):
    def test_split_alpha_and_extract(self):
        png = b"\x89PNG\r\n\x1a\n" + b"maske"
        alfa = b"ALFA" + len(png).to_bytes(4, "big") + png
        jpeg = (b"\xff\xd8"
                + b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                + b"\xff\xe0" + (len(alfa) + 2).to_bytes(2, "big") + alfa
                + b"\x01\x01\x00\x60\x00\x60\x00\x00"                      # Rest-Bytes wie bei EA
                + b"\xff\xdb" + (4).to_bytes(2, "big") + b"\x00\x01"
                + b"\xff\xda" + (2).to_bytes(2, "big") + b"BILDDATEN\xff\xd9")
        clean, alpha = thumbnails.split_alpha(jpeg)
        self.assertEqual(alpha, png)
        self.assertNotIn(b"ALFA", clean)
        self.assertNotIn(b"\x01\x01\x00\x60\x00\x60\x00\x00", clean)
        self.assertTrue(clean.startswith(b"\xff\xd8\xff\xe0") and clean.endswith(b"BILDDATEN\xff\xd9"))
        self.assertEqual(thumbnails.split_alpha(b"\x89PNGxyz"), (b"\x89PNGxyz", None))

        tmp = tempfile.mkdtemp()
        try:
            pkg = os.path.join(tmp, "a.package")
            dbpf.write_package(pkg, [(dbpf.TYPE_CASP, 0, CAS_ID, b"casp"), (0x3C1AF1F2, 0, CAS_ID, jpeg),
                                     (0x3C1AF1F2, 0, CAS_ID + 1, b"kein Bild")])
            self.assertEqual(thumbnails.thumbnails(pkg), [(CAS_ID, jpeg)])
            self.assertEqual(thumbnails.first_thumbnail(pkg), jpeg)
        finally:
            shutil.rmtree(tmp)


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class TrayImageTests(unittest.TestCase):
    def test_decode_and_match_to_entry(self):
        from simvault.analysis import thumbnails
        jpeg = bytes.fromhex("ffd8ffe000104a464946000101") + b"bilddaten" * 20 + b"\xff\xd9"

        def scramble(data, key):
            return bytes(c ^ key[i % 8] for i, c in enumerate(data))

        header = struct.pack("<II8sII", len(jpeg), 0, bytes.fromhex("8efc24489b780e3c"), 2, 0)
        self.assertEqual(thumbnails.decode_tray_image(header + scramble(jpeg, thumbnails.TRAY_IMAGE_KEY)), jpeg)
        other_key = bytes(range(1, 9))                       # unbekannter Schlüssel wird aus dem JPEG-Anfang abgeleitet
        self.assertEqual(thumbnails.decode_tray_image(header + scramble(jpeg, other_key)), jpeg)
        self.assertIsNone(thumbnails.decode_tray_image(header + b"kein bild" * 10))
        tmp = tempfile.mkdtemp()
        try:
            for name in ("0x00000003!0x0abc000000000001.sgi", "0x00000002!0x0abc000000000001.hhi",
                         "0x00000012!0x0abc000000000001.hhi", "0x00000001!0x0abc000000000001.trayitem"):
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(header + scramble(jpeg, thumbnails.TRAY_IMAGE_KEY))
            images = thumbnails.index_tray_images(tmp)
            self.assertEqual(list(images), ["0x0abc000000000001"])
            self.assertTrue(images["0x0abc000000000001"].endswith("0x00000002!0x0abc000000000001.hhi"))
            self.assertEqual(thumbnails.tray_image(images["0x0abc000000000001"]), jpeg)
        finally:
            shutil.rmtree(tmp)


class LotTests(unittest.TestCase):
    def test_snappy_roundtrip_and_errors(self):
        raw = b"abcdefgh" * 50 + bytes(range(256)) + b"xyz" * 40
        self.assertEqual(dbpf.snappy_decompress(snappy_compress(raw)), raw)
        # überlappender Rückverweis (Offset 1 = Byte wiederholen), Literal mit 1-Byte-Länge
        data = varint(70) + bytes([0 << 2]) + b"a" + bytes([((64 - 1) << 2) | 2]) + (1).to_bytes(2, "little") \
            + bytes([((4 - 1) << 2) | 2]) + (1).to_bytes(2, "little") + bytes([0 << 2]) + b"b"
        self.assertEqual(dbpf.snappy_decompress(data), b"a" * 69 + b"b")
        long_lit = bytes([60 << 2, 99]) + bytes(range(100))          # Länge 100 in einem Extra-Byte
        self.assertEqual(dbpf.snappy_decompress(varint(100) + long_lit), bytes(range(100)))
        with self.assertRaises(dbpf.DBPFError):
            dbpf.snappy_decompress(varint(10) + bytes([((4 - 1) << 2) | 2]) + (5).to_bytes(2, "little"))
        with self.assertRaises(dbpf.DBPFError):
            dbpf.snappy_decompress(varint(50) + bytes([3 << 2]) + b"abcd")

    def test_lot_objects_and_missing_cc(self):
        from simvault.analysis import missing_cc
        cc_installed, cc_missing, ea = 0xC9C02F68F16F69D9, 0x2A1452E9643E80AB, 26030
        tmp = tempfile.mkdtemp()
        try:
            tray = os.path.join(tmp, "Tray")
            os.makedirs(tray)
            lot = make_lot([cc_installed, cc_missing, cc_missing, ea, ea])
            with open(os.path.join(tray, "0x00000000!0x068a014ca9912b84.blueprint"), "wb") as f:
                f.write(lot)
            trayitem = (b"\x00" * 8 + f_varint(2, 2) + f_bytes(4, "Circular2".encode()) + f_bytes(7, b"autaki"))
            with open(os.path.join(tray, "0x00000002!0x068a014ca9912b84.trayitem"), "wb") as f:
                f.write(trayitem)
            with open(os.path.join(tray, "0x00000000!0x0000000000000abc.room"), "wb") as f:
                f.write(make_lot([cc_missing]))
            with open(os.path.join(tray, "0x00000000!0x0000000000000def.blueprint"), "wb") as f:
                f.write(b"\x01\x00\x00\x00kaputt")                    # kaputte Datei bricht nichts ab

            self.assertEqual(missing_cc.lot_objects(lot), {cc_installed: 1, cc_missing: 2, ea: 2})
            result = missing_cc.find_missing([], tray, {cc_installed})
            self.assertEqual([p["id"] for p in result["teile"]], [f"0x{cc_missing:016X}"])
            part = result["teile"][0]
            self.assertEqual((part["art"], part["anzahl"]), ("Objekt", 3))
            self.assertIn("Bibliothek „Circular2“: Grundstück (2×)", part["verwendet_von"])
            lots = {h["name"]: h for h in result["bibliothek"]}
            self.assertEqual((lots["Circular2"]["typ"], lots["Circular2"]["ersteller"]), ("Grundstück", "autaki"))
            self.assertEqual(len(lots["Circular2"]["fehlend"]), 1)
            self.assertEqual(lots["0x0000000000000abc"]["typ"], "Raum")      # Raum ohne .trayitem

            used = savegame_analyzer.ids_in_tray(tray, {cc_installed, cc_missing})
            self.assertEqual(used, {cc_installed: 1, cc_missing: 2})       # 1 Grundstück + 1 Raum
        finally:
            shutil.rmtree(tmp)

    def test_real_blueprint_if_available(self):
        import glob
        from simvault.analysis import missing_cc
        files = glob.glob("/mnt/user-data/uploads/Die Sims 4/Tray/*.blueprint")
        if not files:
            self.skipTest("keine echten Bibliotheks-Dateien vorhanden")
        for path in files:
            with open(path, "rb") as f:
                objects = missing_cc.lot_objects(f.read())
            self.assertGreater(sum(objects.values()), 100)


if __name__ == "__main__":
    unittest.main()
