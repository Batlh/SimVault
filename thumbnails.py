# Modul: thumbnails.py
# Funktion: Liest Vorschaubilder aus Sims-4-Paketen.
#
# In CC-Paketen stecken die Vorschaubilder, die das Spiel im CAS bzw. im Kaufmodus zeigt:
#   0x3C1AF1F2  CAS-Teil-Vorschau (JPEG/PNG), meist eine pro Farbvariante
#   0x5B282D45  Körperteil-Vorschau
#   0x3C2A8647  Objekt-Vorschau (Bau-/Kaufmodus)
#   0xCD9DE247  Sim-Vorlagen-Vorschau
# Geprüft an echten Mods: CAS- und Objekt-Vorschauen sind JPEG-Dateien.

import dbpf

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
