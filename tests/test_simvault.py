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
import textwrap

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


# --- Quellen / Erweiterungen --------------------------------------------------

import sources
from sources import loader as source_loader


class RestorePlanTests(unittest.TestCase):
    def _item(self, name, ids, size):
        return {"datei": name, "pfad": "D:\\" + name, "archiv_eintrag": None,
                "ids": [hex(i) for i in ids], "groesse": size}

    def test_no_duplicates_and_installed_skipped(self):
        from cc_finder import plan_restore
        a, b, c = 1 << 40, 2 << 40, 3 << 40
        found = [self._item("Set.package", [a, b], 900), self._item("Wimpern.package", [a], 100),
                 self._item("Schon_da.package", [c], 50)]
        chosen, skipped = plan_restore(found, installed_ids={c})
        self.assertEqual([i["datei"] for i in chosen], ["Set.package"])
        self.assertEqual({n for n, _r in skipped}, {"Wimpern.package", "Schon_da.package"})

    def test_smaller_file_wins_on_tie(self):
        from cc_finder import plan_restore
        a = 1 << 40
        chosen, _ = plan_restore([self._item("Gross.package", [a], 900), self._item("Klein.package", [a], 10)])
        self.assertEqual([i["datei"] for i in chosen], ["Klein.package"])

    def test_sims_hint_not_too_broad(self):
        from cc_finder import looks_like_sims
        self.assertFalse(looks_like_sims(r"F:\games\Mods und setups Mass effect\ALOV.7z"))
        self.assertFalse(looks_like_sims(r"E:\Download\Ocarina of time Patreon.rar"))
        self.assertTrue(looks_like_sims(r"C:\Downloads\MCAS Full Set.7z"))
        self.assertTrue(looks_like_sims(r"D:\Sims4 CC\Haare.zip"))


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
        import conflicts
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
        import conflicts

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
        import conflicts
        result = self._analyze()
        target, moved, failed = conflicts.quarantine(self.mods, [e["datei"] for e in result["entfernbar"]], self.tmp)
        self.assertEqual((moved, failed), (["Wimpern.package"], []))
        self.assertFalse(os.path.exists(os.path.join(self.mods, "Wimpern.package")))
        self.assertTrue(os.path.isfile(os.path.join(target, "Wimpern.package")))
        self.assertEqual(self._analyze()["entfernbar"], [])


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
        import game_locator
        common = self._install("Program Files", "EA Games", "The Sims 4", packs=("EP01", "GP02", "Game"))
        deep = self._install("Zocken", "EA", "Die Sims 4")
        os.makedirs(os.path.join(self.tmp, "Dokumente", "Die Sims 4", "Mods"))    # Benutzerordner: keine Installation
        quick = game_locator.find_game_folders(deep=False, roots=[self.tmp])
        self.assertEqual([(c["pfad"], c["packs"]) for c in quick], [(common, 2)])
        both = game_locator.find_game_folders(deep=True, roots=[self.tmp])
        self.assertEqual([c["pfad"] for c in both], [common, deep])

    def test_steam_library_file(self):
        import game_locator
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
        import game_locator
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
        import repair
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
        import repair
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
        import repair
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
        import repair
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
        import backup_manager
        return [b["name"] for b in backup_manager.list_backups(self.backups) if b["art"] == kind]

    def test_full_restore_modes(self):
        import backup_manager as bm
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
        import backup_manager as bm
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
        import backup_manager as bm
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
        import backup_manager as bm
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
        import updater
        self.assertTrue(updater.is_newer("v0.6.1", "0.6.0"))
        self.assertTrue(updater.is_newer("1.0", "0.9.9"))
        self.assertFalse(updater.is_newer("v0.6.0", "0.6.0"))
        self.assertFalse(updater.is_newer("v0.6", "0.6.0"))
        self.assertFalse(updater.is_newer("v0.5.9", "0.6.0"))
        self.assertFalse(updater.is_newer("", "0.6.0"))

    def test_check_download_and_swap_script(self):
        import io
        import zipfile
        import updater
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
        self.assertEqual(tsr.search_url("Cool Hair"), "https://www.thesimsresource.com/search/Cool+Hair/")
        self.assertFalse(tsr.can_search)

    def test_json_python_override_and_errors(self):
        self._write("simsdom.json", json.dumps({"id": "SimsDom", "name": "SimsDom",
                                                "search_url": "https://simsdom.com/s?q={query}"}))
        self._write("tsr_fix.json", json.dumps([{"id": "tsr", "name": "TSR neu",
                                                 "search_url": "https://tsr.example/{query}"}]))
        self._write("voll.py", textwrap.dedent("""
            from sources.base import Source, SearchResult
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


import thumbnails


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


# --- Programmfenster (nur wenn PySide6 installiert ist) -----------------------

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class TrayImageTests(unittest.TestCase):
    def test_decode_and_match_to_entry(self):
        import thumbnails
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


class GuiSmokeTests(unittest.TestCase):
    def test_window_and_pages_with_data(self):
        import core
        from gui import theme
        from gui.main_window import MainWindow
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


# --- Anmeldungen, Websuche, Downloads (mit lokalem Webserver, ohne Internet) ----------

import threading
import http.server


class _Handler(http.server.BaseHTTPRequestHandler):
    """Kleiner Test-Server: liefert Dateien aus FILES, prüft Cookies, simuliert eine Login-Seite."""
    FILES = {}
    seen_cookies = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        _Handler.seen_cookies.append(self.headers.get("Cookie", ""))
        path = self.path.split("?")[0]
        if path == "/login-noetig":
            body, ctype = b"<!DOCTYPE html><html>Bitte anmelden</html>", "text/html; charset=utf-8"
            disposition = None
        elif path in self.FILES:
            body, ctype, disposition = self.FILES[path]
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        self.wfile.write(body)


def start_server(files):
    _Handler.FILES = files
    _Handler.seen_cookies = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class SecureStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_encrypted_roundtrip_and_tamper(self):
        import secure_store
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
        import secure_store
        store = secure_store.SecureStore(self.tmp, protect=(lambda k: b"P" + bytes(b ^ 0x55 for b in k),
                                                            lambda k: bytes(b ^ 0x55 for b in k[1:])))
        store.save("x", [{"name": "a", "value": "b", "domain": "x.com"}])
        with open(store.key_path, "rb") as f:
            self.assertTrue(f.read().startswith(b"P"))
        self.assertEqual(len(store.cookies("x")), 1)

    @unittest.skipUnless(os.name == "nt", "nur Windows (DPAPI)")
    def test_windows_dpapi(self):
        import secure_store
        blob = secure_store._dpapi(b"k" * 32, True)
        self.assertNotEqual(blob, b"k" * 32)
        self.assertEqual(secure_store._dpapi(blob, False), b"k" * 32)

    def test_cookie_header_rules(self):
        from secure_store import cookie_header
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
        import downloads
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
        import downloads
        page = os.path.join(self.tmp, "datei.package")
        with open(page, "w") as f:
            f.write("<!DOCTYPE html><html>Login</html>")
        result = downloads.install(page, self.mods, self.tray)
        self.assertIn("beschädigt", result["fehler"][0][1])
        html = os.path.join(self.tmp, "seite.htm")
        with open(html, "w") as f:
            f.write("<html>Login</html>")
        self.assertIn("Webseite", downloads.install(html, self.mods, self.tray)["fehler"][0][1])

    def test_download_with_cookies_and_login_page(self):
        import secure_store
        import web_session
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
        import core
        import sources.loader as loader
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
                    from sources.base import Source, SearchResult
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
            cfg = {"plugin_folders": [tmp], "sources_enabled": {}}
            results, links, errors = core.web_search(cfg, "Kijiko", session=core.web_session(cfg))
            self.assertEqual([(r.title, r.creator, r.extra["bild"]) for r in results],
                             [("Kijiko Wimpern", "Kijiko", b"\xff\xd8bild1"),
                              ("Kijiko Haare", "Kijiko", b"\xff\xd8bild2")])
            self.assertEqual(results[0].extra["quelle"], "Testseite")
            self.assertEqual(errors, [("Kaputte Seite", "Seite antwortet nicht")])
            self.assertIn("Testseite", links)
            self.assertIn("The Sims Resource", links)                       # Link-Quellen weiter dabei
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
        import secure_store
        from PySide6.QtCore import QTimer
        from gui.browser import BrowserCore
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
        import database
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
        import database
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
        import database
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
        import i18n
        i18n.set_language("de")

    def test_tr_exact_patterns_and_german_default(self):
        import i18n
        i18n.set_language("de")
        self.assertEqual(i18n.tr("genutzt"), "genutzt")
        i18n.set_language("en")
        self.assertEqual(i18n.tr("genutzt"), "used")
        self.assertEqual(i18n.tr("Aufräumen (3)"), "Clean up (3)")
        self.assertEqual(i18n.tr("installiert: 2× Paket; 1 übersprungen"), "installed: 2× package; 1 skipped")
        self.assertEqual(i18n.tr("Unbekannter Satz"), "Unbekannter Satz")
        self.assertEqual(i18n.set_language("xx"), "de")

    def test_catalog_has_no_placeholder_mismatch(self):
        import i18n
        for src, dst in i18n.EN.items():
            self.assertEqual(src.count("{}"), dst.count("{}"), src)

    @unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
    def test_translate_widget_once(self):
        import i18n
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


# --- Bibliothek: Grundstücke und Räume (.blueprint/.room, Snappy) ----------------------

def snappy_compress(raw):
    """Kleiner Snappy-Packer für Tests: Literale plus Rückverweise auf wiederholte 8-Byte-Blöcke."""
    out = bytearray(varint(len(raw)))
    pos, lit_start, seen = 0, 0, {}

    def literal(chunk):
        while chunk:
            part, chunk = chunk[:60], chunk[60:]
            out.append((len(part) - 1) << 2)
            out.extend(part)

    while pos + 8 <= len(raw):
        key = raw[pos:pos + 8]
        prev = seen.get(key)
        seen[key] = pos
        if prev is not None and pos - prev < 65536:
            length = 8
            while pos + length < len(raw) and length < 64 and raw[prev + length] == raw[pos + length]:
                length += 1
            literal(raw[lit_start:pos])
            out.append(((length - 1) << 2) | 2)
            out.extend((pos - prev).to_bytes(2, "little"))
            pos += length
            lit_start = pos
        else:
            pos += 1
    literal(raw[lit_start:])
    return bytes(out)


def make_lot(definitions):
    """Baut eine .blueprint-Datei wie das Spiel: Kopf, Snappy, Kennung, Protobuf mit Objekten, LDNB-Teil."""
    proto = f_varint(1, 961473792)
    for i, definition in enumerate(definitions):
        obj = f_varint(1, 0x068A014C00000000 + i) + f_bytes(3, f_bytes(1, b"\x0d\x00\x00\x30\x41" * 3))
        obj += f_varint(15, definition)
        proto += f_bytes(2, obj)
    raw = struct.pack("<III", 0xFEA1BAAD, 1, len(proto)) + proto + b"\x01\x00\x00\x00" * 2 + b"LDNB" + b"\x00" * 300
    packed = snappy_compress(raw)
    return struct.pack("<II", 1, len(packed)) + packed


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
        import missing_cc
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
        import missing_cc
        files = glob.glob("/mnt/user-data/uploads/Die Sims 4/Tray/*.blueprint")
        if not files:
            self.skipTest("keine echten Bibliotheks-Dateien vorhanden")
        for path in files:
            with open(path, "rb") as f:
                objects = missing_cc.lot_objects(f.read())
            self.assertGreater(sum(objects.values()), 100)
