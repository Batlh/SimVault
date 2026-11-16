# Gemeinsame Hilfen für die Tests: selbst gebaute Pakete, Spielstände, Bibliothek, kleiner Webserver.
# Die Tests selbst liegen nach Bereichen in test_analysis.py, test_finder.py, test_web.py, test_sites.py, test_app.py.
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

os.environ["SIMVAULT_LANG"] = "de"      # Tests erwarten deutsche Texte, egal welche Sprache das System hat

from simvault.analysis import dbpf

import main

from simvault.analysis import mod_folder_scanner

from simvault.analysis import savegame_analyzer

from simvault.finder import cc_searcher

CAS_ID = 0xA1B2C3D4E5F60718

CAS_ID_2 = 0x9988776655443322

OBJ_ID = 0xF00DFACE12345678

UNUSED_CAS_ID = 0x1234567890ABCDEF

TUNING_ID = 0xCAFEBABE00000042

TRAY_ONLY_ID = 0xDEADBEEF87654321

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

from simvault.analysis import missing_cc

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

import zipfile as _zipfile

from simvault.finder import cc_finder

from simvault.finder import archive_tools

from simvault.web import sources

from simvault.web.sources import loader as source_loader

from simvault.analysis import thumbnails

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

try:
    import cryptography  # noqa: F401  (für verschlüsselte Anmeldungen)
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

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


# Auch Namen mit „_“ (z. B. _zipfile) an die Testdateien weitergeben
__all__ = [name for name in dir() if not name.startswith("__")]
