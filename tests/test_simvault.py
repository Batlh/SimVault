# Tests für SimVault mit selbst erzeugten Paketen und Spielständen.
# Ausführen:  python -m unittest discover -s tests -v

import os
import sys
import json
import struct
import shutil
import sqlite3
import tempfile
import unittest
import zlib
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import dbpf
import main
import mod_folder_scanner
import savegame_analyzer
import cc_searcher

CAS_ID = 0xA1B2C3D4E5F60718
CAS_ID_2 = 0x9988776655443322
OBJ_ID = 0xF00DFACE12345678
UNUSED_CAS_ID = 0x1234567890ABCDEF
TUNING_ID = 0xCAFEBABE00000042
TRAY_ONLY_ID = 0xDEADBEEF87654321


# --- kleine Protobuf-Helfer -------------------------------------------------

def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def f_varint(field, value):
    return varint(field << 3) + varint(value)


def f_fixed64(field, value):
    return varint((field << 3) | 1) + struct.pack("<Q", value)


def f_bytes(field, data):
    return varint((field << 3) | 2) + varint(len(data)) + data


def make_savegame_proto(cas_ids, obj_ids, tuning_ids=()):
    """Grob wie ein Spielstand aufgebaut: Sims mit Outfits (gepackte ID-Liste), Objekte, Merkmale."""
    outfit = f_varint(1, 777) + f_bytes(5, b"".join(varint(i) for i in cas_ids))
    sim = f_varint(1, 123456) + f_bytes(2, "Bella Grusel".encode()) + f_bytes(9, f_bytes(1, outfit))
    for t in tuning_ids:
        sim += f_varint(14, t)
    zone = f_varint(1, 42)
    for o in obj_ids:
        zone += f_bytes(3, f_fixed64(1, o) + f_varint(2, 5))
    return f_bytes(1, f_varint(1, 1)) + f_bytes(4, sim) + f_bytes(6, zone)


def refpack_literals(data):
    """Minimaler RefPack-Encoder (nur Literale) für Tests."""
    out = bytearray([0x10, 0xFB]) + len(data).to_bytes(3, "big")
    pos = 0
    while len(data) - pos >= 4:
        n = min(112, (len(data) - pos) // 4 * 4)
        out.append(0xE0 + ((n - 4) >> 2))
        out += data[pos:pos + n]
        pos += n
    rest = len(data) - pos
    out.append(0xFC + rest)
    out += data[pos:]
    return bytes(out)


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


def build_sims_folder(root):
    """Legt einen kompletten Test-Sims-Ordner an."""
    sims = os.path.join(root, "Electronic Arts", "Die Sims 4")
    mods = os.path.join(sims, "Mods")
    saves = os.path.join(sims, "saves")
    tray = os.path.join(sims, "Tray")
    for d in (mods, saves, tray):
        os.makedirs(d)

    def pkg(rel, resources):
        path = os.path.join(mods, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        dbpf.write_package(path, resources)

    pkg("CAS/Haare/[Creator] Cool_Hair.package", [(dbpf.TYPE_CASP, 0x80000000, CAS_ID, b"casp")])
    pkg("CAS/Kleid.package", [(dbpf.TYPE_CASP, 0x80000000, CAS_ID_2, b"casp2")])
    pkg("CAS/Ungenutzt.package", [(dbpf.TYPE_CASP, 0x80000000, UNUSED_CAS_ID, b"casp3")])
    pkg("BuyBuild/Sofa.package", [(dbpf.TYPE_OBJD, 0, OBJ_ID, b"objd"), (dbpf.TYPE_COBJ, 0, OBJ_ID, b"cobj")])
    pkg("Tray/TrayCC.package", [(dbpf.TYPE_CASP, 0, TRAY_ONLY_ID, b"casp4")])
    pkg("Gameplay/Trait.package", [(0x62E94D38, 0, TUNING_ID, b"<I/>")])
    pkg("Gameplay/AndererMod.package", [(0x62E94D38, 0, 0xABCDEF0123456789, b"<I/>")])
    pkg("a/b/c/d/e/f/ZuTief.package", [(dbpf.TYPE_CASP, 0, 0x5555555555555555, b"x")])
    # Merge, der das Kleid noch einmal enthält -> Konflikt
    pkg("Merged/Merge (Merged).package", [(dbpf.TYPE_CASP, 0x80000000, CAS_ID_2, b"casp2"),
                                           (dbpf.TYPE_CASP, 0, 0x7777777777777777, b"y")])
    # Duplikat
    shutil.copy(os.path.join(mods, "CAS", "Kleid.package"), os.path.join(mods, "Kleid Kopie.package"))
    with open(os.path.join(mods, "Kaputt.package"), "wb") as f:
        f.write(b"Das ist kein Paket" * 20)
    open(os.path.join(mods, "Leer.package"), "wb").close()
    import zipfile
    for rel in ("MeinScript.ts4script", "Scripts/Ok.ts4script", "Scripts/Zu/Tief.ts4script"):
        path = os.path.join(mods, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("x.pyc", rel.encode())
    open(os.path.join(mods, "Download.zip"), "wb").close()

    # Spielstand: Spielstand-Daten zlib-komprimiert, dazu ein RefPack-Thumbnail
    proto = make_savegame_proto([CAS_ID, CAS_ID_2, 0x0000000000001234], [OBJ_ID], [TUNING_ID])
    save = os.path.join(saves, "Slot_00000001.save")
    dbpf.write_package(save, [(dbpf.TYPE_SAVEGAME_DATA, 0, 1, proto, True),
                              (0x3BD45407, 0, 2, os.urandom(5000))])
    dbpf.write_package(os.path.join(saves, "Slot_00000001.save.ver0"), [(dbpf.TYPE_SAVEGAME_DATA, 0, 1, b"")])

    # Tray: Haushalt mit kurzem Kopf vor den Protobuf-Daten
    hh = struct.pack("<II", 1, 0) + make_savegame_proto([TRAY_ONLY_ID], [])
    with open(os.path.join(tray, "0x00000002!0x0a1b2c3d4e5f6789.householdbinary"), "wb") as f:
        f.write(hh)
    return sims


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
            self.assertIn("thesimsresource.com/search/Kaputt/", html)
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


class SearchTests(unittest.TestCase):
    def test_query_from_filename(self):
        self.assertEqual(cc_searcher.query_from_filename("[Creator] Cool_Hair-v2 (Merged).package"), "Creator Cool Hair v2")
        self.assertIn("Cool+Hair", cc_searcher.search_links("Cool_Hair.package")["CurseForge"])


if __name__ == "__main__":
    unittest.main()


# --- Fehlende CC -------------------------------------------------------------

import missing_cc

MISSING_CAS = 0xF0D922ECD3F09373
MISSING_OBJ = 0xBEEF0000CAFE0001
MISSING_TRAY_CAS = 0xDD3010EF4E9C62C7
EA_CAS = 0x0000000000012345
ZONE_ID = 48436494820966430


def packed_fixed64(values):
    return b"".join(struct.pack("<Q", v) for v in values)


def sim_proto(first, last, cas_ids, extra_cas=(), inventory=(), body_types=None):
    outfit = f_varint(1, 99) + f_bytes(5, f_bytes(1, packed_fixed64(cas_ids)))
    if body_types:
        outfit += f_bytes(7, f_bytes(1, b"".join(varint(t) for t in body_types)))
    sim = f_fixed64(1, 123) + f_bytes(5, first.encode()) + f_bytes(6, last.encode())
    sim += f_bytes(21, f_bytes(1, outfit))
    for c in extra_cas:
        sim += f_bytes(28, f_bytes(5, f_bytes(1, f_varint(1, c) + f_varint(2, 2))))
    if inventory:
        sim += f_bytes(20, b"".join(f_bytes(1, f_varint(30, o)) for o in inventory))
    return sim


def build_real_layout_save(path):
    sims = f_bytes(6, sim_proto("Bella", "Grusel", [EA_CAS, CAS_ID, MISSING_CAS], extra_cas=[MISSING_CAS],
                                inventory=[OBJ_ID, MISSING_OBJ], body_types=[6, 7, 2]))
    household = f_bytes(5, f_bytes(3, b"Grusel") + f_bytes(6, f_bytes(1, f_varint(30, MISSING_OBJ))))
    zone_info = f_bytes(7, f_fixed64(1, ZONE_ID) + f_bytes(2, "Gut Eichhof".encode()))
    savegame = f_bytes(1, f_varint(1, 1)) + household + sims + zone_info
    zone = f_bytes(3, f_bytes(1, f_varint(30, 0x17B94)) + f_bytes(1, f_varint(30, MISSING_OBJ)))
    dbpf.write_package(path, [(dbpf.TYPE_SAVEGAME_DATA, 0, 1, savegame, True), (0x6, 0, ZONE_ID, zone, True)])


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


# --- Fundgrube --------------------------------------------------------------

import zipfile as _zipfile
import cc_finder


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
            self.assertEqual(cc_finder.restore(grouped, other, exclude=["ivka"]), [])

            # erneutes Zurückholen überschreibt nichts
            self.assertEqual(cc_finder.restore([{"datei": "Sofa.package", "pfad": "egal", "archiv_eintrag": None}],
                                               mods), [])
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
            locs = cc_finder.search_locations({}, [a, os.path.join(a, "Unterordner"), os.path.join(tmp, "fehlt")])
            self.assertEqual(locs, [a])
            # Systemordner (hier "Windows") werden übersprungen
            hits, _ = cc_finder.search(locs, {MISSING_CAS})
            self.assertEqual(hits, [])
            if os.name != "nt":
                self.assertEqual(cc_finder.list_drives(), [])
        finally:
            shutil.rmtree(tmp)


# --- RAR/7z ------------------------------------------------------------------

import archive_tools


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
        created = cc_finder.restore(found, mods)
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
        created = cc_finder.restore(found, os.path.join(self.tmp, "Mods3"))
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
