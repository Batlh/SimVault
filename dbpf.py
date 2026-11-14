# Modul: dbpf.py
# Funktion: Liest Sims-4-Pakete im DBPF-2.x-Format (.package, .save, viele Tray-Dateien)
#
# Aufbau einer DBPF-Datei:
# - 96 Byte Header (Magic "DBPF", Version 2.1, Anzahl/Position/Größe des Index)
# - Ressourcen-Daten (roh, zlib- oder RefPack-komprimiert)
# - Index: pro Ressource Typ, Gruppe, Instanz (64 Bit), Offset, Größe, Kompression
#
# Für die meisten Auswertungen reicht der Index (schnell, kein Entpacken).
# Ressourcen werden nur bei Bedarf gelesen und entpackt.

import struct
import zlib
from dataclasses import dataclass

DBPF_MAGIC = b"DBPF"
HEADER_SIZE = 96

# Kompressionsarten im Index
COMPRESSION_NONE = 0x0000
COMPRESSION_ZLIB = 0x5A42
COMPRESSION_REFPACK = 0xFFFF
COMPRESSION_STREAMABLE = 0xFFFE
COMPRESSION_DELETED = 0xFFE0

# Wichtige Ressourcentypen
TYPE_CASP = 0x034AEECB         # CAS-Teil (Kleidung, Haare, Accessoires, ...)
TYPE_OBJD = 0xC0DB5AE7         # Objektdefinition (Bau-/Kaufmodus)
TYPE_COBJ = 0x319E4F1D         # Katalogobjekt (Bau-/Kaufmodus)
TYPE_SAVEGAME_DATA = 0x0000000D  # Spielstand-Daten (Protobuf) in .save-Dateien

CONTENT_TYPES = {
    TYPE_CASP: "CAS",
    TYPE_OBJD: "Objekt",
    TYPE_COBJ: "Objekt",
}


class DBPFError(Exception):
    """Datei ist kein gültiges oder ein beschädigtes DBPF-Paket."""


@dataclass(frozen=True)
class ResourceEntry:
    type: int
    group: int
    instance: int
    offset: int
    file_size: int
    mem_size: int
    compression: int

    @property
    def tgi(self):
        return (self.type, self.group, self.instance)

    def tgi_str(self):
        return f"{self.type:08X}:{self.group:08X}:{self.instance:016X}"


def read_index(path, strict=True):
    """Liest nur Header und Index eines Pakets. Gibt eine Liste von ResourceEntry zurück.
    strict=False: Einträge, die hinter das Dateiende zeigen, werden trotzdem geliefert (für Reparaturen)."""
    with open(path, "rb") as f:
        return read_index_fileobj(f, strict)


def read_index_bytes(data):
    """Wie read_index, aber für ein Paket im Speicher (z. B. aus einem ZIP-Archiv)."""
    import io
    return read_index_fileobj(io.BytesIO(data))


def read_index_fileobj(f, strict=True):
    header = f.read(HEADER_SIZE)
    if len(header) < HEADER_SIZE or header[:4] != DBPF_MAGIC:
        raise DBPFError("Kein DBPF-Paket (Magic fehlt oder Datei zu kurz)")
    major, minor = struct.unpack_from("<II", header, 4)
    if major != 2:
        raise DBPFError(f"Nicht unterstützte DBPF-Version {major}.{minor}")

    index_count = struct.unpack_from("<I", header, 36)[0]
    index_size = struct.unpack_from("<I", header, 44)[0]
    index_pos = struct.unpack_from("<I", header, 64)[0] or struct.unpack_from("<I", header, 40)[0]

    if index_count == 0:
        return []

    f.seek(0, 2)
    file_len = f.tell()
    if index_pos == 0 or index_pos + index_size > file_len:
        raise DBPFError("Index liegt außerhalb der Datei (Paket beschädigt/abgeschnitten)")
    f.seek(index_pos)
    index = f.read(index_size)
    return _parse_index(index, index_count, file_len, strict)


def _parse_index(index, count, file_len, strict=True):
    try:
        pos = 0
        flags = struct.unpack_from("<I", index, pos)[0]
        pos += 4
        const_type = const_group = const_inst_hi = None
        if flags & 0x1:
            const_type = struct.unpack_from("<I", index, pos)[0]; pos += 4
        if flags & 0x2:
            const_group = struct.unpack_from("<I", index, pos)[0]; pos += 4
        if flags & 0x4:
            const_inst_hi = struct.unpack_from("<I", index, pos)[0]; pos += 4

        entries = []
        for _ in range(count):
            if const_type is None:
                rtype = struct.unpack_from("<I", index, pos)[0]; pos += 4
            else:
                rtype = const_type
            if const_group is None:
                group = struct.unpack_from("<I", index, pos)[0]; pos += 4
            else:
                group = const_group
            if const_inst_hi is None:
                inst_hi = struct.unpack_from("<I", index, pos)[0]; pos += 4
            else:
                inst_hi = const_inst_hi
            inst_lo, offset, size_raw, mem_size = struct.unpack_from("<IIII", index, pos)
            pos += 16

            compression = COMPRESSION_NONE
            if size_raw & 0x80000000:
                compression = struct.unpack_from("<H", index, pos)[0]
                pos += 4  # Kompression (u16) + "committed" (u16)
            file_size = size_raw & 0x7FFFFFFF

            if strict and compression != COMPRESSION_DELETED and offset + file_size > file_len:
                raise DBPFError("Ressource zeigt hinter das Dateiende (Paket beschädigt)")

            entries.append(ResourceEntry(rtype, group, (inst_hi << 32) | inst_lo,
                                         offset, file_size, mem_size, compression))
        return entries
    except struct.error as e:
        raise DBPFError(f"Index unvollständig: {e}") from None


def read_resource(path, entry):
    """Liest eine Ressource und gibt die entpackten Bytes zurück."""
    with open(path, "rb") as f:
        f.seek(entry.offset)
        raw = f.read(entry.file_size)
    return decompress(raw, entry.compression)


def decompress(raw, compression):
    if compression == COMPRESSION_NONE:
        return raw
    if compression == COMPRESSION_ZLIB:
        return zlib.decompress(raw)
    if compression in (COMPRESSION_REFPACK, COMPRESSION_STREAMABLE):
        return refpack_decompress(raw)
    if compression == COMPRESSION_DELETED:
        return b""
    raise DBPFError(f"Unbekannte Kompression 0x{compression:04X}")


def refpack_decompress(data):
    """Entpackt EAs RefPack/QFS-Kompression (in Sims 4 'internal compression')."""
    if len(data) < 2 or data[1] != 0xFB:
        raise DBPFError("Kein RefPack-Header")
    flags = data[0]
    if flags & 0x80:
        size = int.from_bytes(data[2:6], "big"); pos = 6
    else:
        size = int.from_bytes(data[2:5], "big"); pos = 5

    out = bytearray()
    n = len(data)
    while pos < n:
        b0 = data[pos]
        if b0 < 0x80:
            b1 = data[pos + 1]; pos += 2
            plain = b0 & 0x03
            copy_len = ((b0 & 0x1C) >> 2) + 3
            copy_off = ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = data[pos + 1], data[pos + 2]; pos += 3
            plain = (b1 >> 6) & 0x03
            copy_len = (b0 & 0x3F) + 4
            copy_off = ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]; pos += 4
            plain = b0 & 0x03
            copy_len = ((b0 & 0x0C) << 6) + b3 + 5
            copy_off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            pos += 1
            plain = ((b0 & 0x1F) << 2) + 4
            copy_len = 0
            copy_off = 0
        else:
            pos += 1
            plain = b0 & 0x03
            out += data[pos:pos + plain]
            break

        out += data[pos:pos + plain]
        pos += plain
        if copy_len:
            start = len(out) - copy_off
            if start < 0:
                raise DBPFError("RefPack: ungültiger Rückverweis")
            if copy_off >= copy_len:
                out += out[start:start + copy_len]
            else:  # überlappende Kopie, byteweise
                for i in range(copy_len):
                    out.append(out[start + i])

    if len(out) != size:
        raise DBPFError(f"RefPack: erwartete {size} Bytes, erhalten {len(out)}")
    return bytes(out)


def write_package(path, resources):
    """Schreibt ein einfaches DBPF-Paket. resources: Liste von (type, group, instance, bytes[, compress]).
    Gedacht für Tests und Export, nicht als vollwertiger Paket-Editor."""
    body = bytearray(b"\0" * HEADER_SIZE)
    index_entries = []
    for res in resources:
        rtype, group, instance, data = res[:4]
        use_zlib = res[4] if len(res) > 4 else False
        stored = zlib.compress(data) if use_zlib else data
        offset = len(body)
        body += stored
        index_entries.append((rtype, group, instance, offset, len(stored), len(data),
                              COMPRESSION_ZLIB if use_zlib else COMPRESSION_NONE))

    index_pos = len(body)
    index = bytearray(struct.pack("<I", 0))
    for rtype, group, instance, offset, fsize, msize, comp in index_entries:
        index += struct.pack("<IIIIIIIHH", rtype, group, instance >> 32, instance & 0xFFFFFFFF,
                             offset, fsize | 0x80000000, msize, comp, 1)
    body += index

    header = bytearray(HEADER_SIZE)
    header[0:4] = DBPF_MAGIC
    struct.pack_into("<II", header, 4, 2, 1)
    struct.pack_into("<I", header, 36, len(index_entries))
    struct.pack_into("<I", header, 44, len(index))
    struct.pack_into("<I", header, 60, 3)
    struct.pack_into("<I", header, 64, index_pos)
    body[0:HEADER_SIZE] = header

    with open(path, "wb") as f:
        f.write(body)


def rebuild_package(source, target, entries):
    """Schreibt ein neues Paket nur mit den angegebenen Ressourcen aus source.
    Die Daten werden unverändert (weiter komprimiert) übernommen – für Reparaturen."""
    index = bytearray(struct.pack("<I", 0))
    with open(source, "rb") as src, open(target, "wb") as dst:
        dst.write(b"\0" * HEADER_SIZE)
        offset = HEADER_SIZE
        count = 0
        for e in entries:
            if e.compression == COMPRESSION_DELETED:
                continue
            src.seek(e.offset)
            raw = src.read(e.file_size)
            dst.write(raw)
            index += struct.pack("<IIIIIIIHH", e.type, e.group, e.instance >> 32, e.instance & 0xFFFFFFFF,
                                 offset, len(raw) | 0x80000000, e.mem_size, e.compression, 1)
            offset += len(raw)
            count += 1
        dst.write(index)
        header = bytearray(HEADER_SIZE)
        header[0:4] = DBPF_MAGIC
        struct.pack_into("<II", header, 4, 2, 1)
        struct.pack_into("<I", header, 36, count)
        struct.pack_into("<I", header, 44, len(index))
        struct.pack_into("<I", header, 60, 3)
        struct.pack_into("<I", header, 64, offset)
        dst.seek(0)
        dst.write(header)
    return count
