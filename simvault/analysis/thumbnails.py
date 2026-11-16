# Modul: simvault/analysis/thumbnails.py
# Funktion: Liest Vorschaubilder aus Sims-4-Paketen.
#
# In CC-Paketen stecken die Vorschaubilder, die das Spiel im CAS bzw. im Kaufmodus zeigt:
#   0x3C1AF1F2  CAS-Teil-Vorschau (JPEG/PNG), meist eine pro Farbvariante
#   0x5B282D45  Körperteil-Vorschau
#   0x3C2A8647  Objekt-Vorschau (Bau-/Kaufmodus)
#   0xCD9DE247  Sim-Vorlagen-Vorschau
# Geprüft an echten Mods: CAS- und Objekt-Vorschauen sind JPEG-Dateien.
#
# Die Vorschaubilder der Bibliothek (Tray: .hhi Haushalt, .sgi Sim, .bpi Grundstück, .rmi Raum) sind
# dieselben JPEGs (mit ALFA-Maske), aber verschleiert: 24 Byte Kopf (Länge, Kennung, Art), danach sind die
# Bilddaten Byte für Byte mit einem 8-Byte-Schlüssel XOR-verknüpft. Geprüft an echten .hhi-Dateien.

import os

from simvault.analysis import dbpf

THUMBNAIL_TYPES = (0x3C1AF1F2, 0x5B282D45, 0x3C2A8647, 0xCD9DE247)
IMAGE_SIGNATURES = (b"\xff\xd8", b"\x89PNG")


def thumbnails(path, limit=None):
    """Vorschaubilder eines Pakets als Liste von (Instanz-ID, Bilddaten)."""
    result = []
    try:
        entries = dbpf.read_index(path)
    except (dbpf.DBPFError, OSError):
        return result
    for entry in entries:
        if entry.type not in THUMBNAIL_TYPES:
            continue
        try:
            data = dbpf.read_resource(path, entry)
        except Exception:  # einzelnes kaputtes Bild überspringen
            continue
        if data.startswith(IMAGE_SIGNATURES):
            result.append((entry.instance, data))
            if limit and len(result) >= limit:
                break
    return result


def first_thumbnail(path):
    """Erstes Vorschaubild eines Pakets (Bilddaten) oder None."""
    found = thumbnails(path, limit=1)
    return found[0][1] if found else None


def split_alpha(data):
    """Trennt EAs eingebettete Transparenzmaske vom JPEG.

    Sims-4-Vorschaubilder sind JPEGs mit einem zusätzlichen APP0-Block "ALFA", der ein PNG mit der
    Transparenz enthält; danach folgen oft einige Rest-Bytes, über die Bildprogramme stolpern.
    Gibt (sauberes JPEG, PNG-Maske oder None) zurück. Andere Bilder kommen unverändert zurück."""
    if not data.startswith(b"\xff\xd8"):
        return data, None
    out = bytearray(b"\xff\xd8")
    alpha = None
    pos = 2
    n = len(data)
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            nxt = data.find(b"\xff", pos)      # Rest-Bytes nach dem ALFA-Block überspringen
            if nxt < 0:
                break
            pos = nxt
            continue
        marker = data[pos + 1]
        if marker == 0xFF:                      # Füllbyte
            pos += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            out += data[pos:pos + 2]
            pos += 2
            continue
        if marker == 0xDA:                      # ab hier Bilddaten bis zum Ende
            out += data[pos:]
            return bytes(out), alpha
        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        segment = data[pos:pos + 2 + length]
        payload = segment[4:]
        if marker == 0xE0 and payload.startswith(b"ALFA"):
            start = payload.find(b"\x89PNG")
            if start >= 0:
                alpha = bytes(payload[start:])
        else:
            out += segment
        pos += 2 + length
    return bytes(out), alpha


# ---------------------------------------------------------------------------
# Vorschaubilder der Bibliothek (Tray)
# ---------------------------------------------------------------------------

TRAY_IMAGE_EXTENSIONS = (".hhi", ".bpi", ".rmi", ".sgi")     # Reihenfolge = Vorrang als Bild eines Eintrags
TRAY_IMAGE_HEADER = 24
TRAY_IMAGE_KEY = bytes.fromhex("4125e6cd47bab21a")
_JPEG_START = bytes.fromhex("ffd8ffe000104a46")              # FF D8 FF E0 00 10 "JF"


def _xor(data, key):
    repeated = (key * (len(data) // len(key) + 1))[:len(data)]
    return (int.from_bytes(data, "little") ^ int.from_bytes(repeated, "little")).to_bytes(len(data), "little")


def decode_tray_image(data):
    """Entschlüsselt ein Bibliotheks-Vorschaubild. Gibt die Bilddaten (JPEG, evtl. mit ALFA-Maske) zurück
    oder None, wenn die Datei nicht passt."""
    if len(data) <= TRAY_IMAGE_HEADER + 16:
        return None
    body = data[TRAY_IMAGE_HEADER:]
    if body.startswith(IMAGE_SIGNATURES):                     # unverschleiert
        return body
    image = _xor(body, TRAY_IMAGE_KEY)
    if not image.startswith(IMAGE_SIGNATURES):
        # anderer Schlüssel: aus dem bekannten JPEG-Anfang ableiten und am "JFIF" gegenprüfen
        key = bytes(a ^ b for a, b in zip(body[:8], _JPEG_START))
        image = _xor(body, key)
        if image[6:10] != b"JFIF":
            return None
    return image


def index_tray_images(tray_folder):
    """{Eintrags-ID (wie in missing_cc): Pfad des besten Vorschaubilds} für alle Bibliothekseinträge."""
    best = {}
    try:
        names = os.listdir(tray_folder)
    except OSError:
        return best
    for name in names:
        low = name.lower()
        ext = os.path.splitext(low)[1]
        if ext not in TRAY_IMAGE_EXTENSIONS or "!" not in low:
            continue
        prefix, rest = low.split("!", 1)
        item_id = rest.rsplit(".", 1)[0]
        rank = (TRAY_IMAGE_EXTENSIONS.index(ext), prefix)     # Haushaltsbild vor Einzelbildern, erstes Bild zuerst
        if item_id not in best or rank < best[item_id][0]:
            best[item_id] = (rank, os.path.join(tray_folder, name))
    return {item_id: path for item_id, (_rank, path) in best.items()}


def tray_image(path):
    """Bilddaten eines Bibliotheks-Vorschaubilds (oder None)."""
    try:
        with open(path, "rb") as f:
            return decode_tray_image(f.read())
    except OSError:
        return None
