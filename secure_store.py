# Modul: secure_store.py
# Funktion: Speichert Anmeldungen (Cookies) für CC-Seiten verschlüsselt – nie im Klartext auf der Platte.
#
# Aufbau:
# - Die Cookies liegen in einer Datei logins.bin, verschlüsselt mit AES-256-GCM (Verschlüsselung und
#   Manipulationsschutz in einem). Entschlüsselt wird nur im Arbeitsspeicher, solange SimVault läuft.
# - Der 256-Bit-Schlüssel ist zufällig und liegt selbst geschützt daneben (logins.key):
#     Windows:  mit der Windows-Datenschutz-API (DPAPI) an das Benutzerkonto gebunden – auf einem anderen
#               PC oder unter einem anderen Windows-Benutzer lässt er sich nicht entschlüsseln.
#     sonst:    Datei nur für den eigenen Benutzer lesbar (chmod 600) – schwächer, das Programm sagt das.
# - Gespeichert wird pro Quelle (z. B. "patreon"): Liste der Cookies und wann die Anmeldung gespeichert wurde.
#   Passwörter werden nie gespeichert – nur die Cookies, die die Seite nach dem Anmelden setzt.

import os
import json
import time
import secrets
import logging

log = logging.getLogger(__name__)

MAGIC = b"SVL1"
NONCE_SIZE = 12


class StoreError(Exception):
    """Gespeicherte Anmeldungen lassen sich nicht lesen (Schlüssel fehlt, Datei verändert …)."""


# ---------------------------------------------------------------------------
# Schlüsselschutz
# ---------------------------------------------------------------------------

def _dpapi(data, protect):
    """Windows-DPAPI (CryptProtectData/CryptUnprotectData) über ctypes."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = Blob()
    entropy_data = b"SimVault-Anmeldungen"
    ebuf = ctypes.create_string_buffer(entropy_data, len(entropy_data))
    entropy = Blob(len(entropy_data), ctypes.cast(ebuf, ctypes.POINTER(ctypes.c_char)))
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    func = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect:
        ok = func(ctypes.byref(blob_in), "SimVault", ctypes.byref(entropy), None, None,
                  CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    else:
        ok = func(ctypes.byref(blob_in), None, ctypes.byref(entropy), None, None,
                  CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise StoreError("Windows konnte den Schlüssel nicht " + ("schützen" if protect else "entsperren"))
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def key_protection():
    """Wie der Schlüssel geschützt ist – für die Anzeige."""
    return "Windows-Benutzerkonto (DPAPI)" if os.name == "nt" else "Dateirechte (nur dieser Benutzer)"


class SecureStore:
    """Verschlüsselter Speicher für Anmeldungen. folder: z. B. %APPDATA%\\SimVault"""

    def __init__(self, folder, protect=None):
        self.folder = folder
        self.data_path = os.path.join(folder, "logins.bin")
        self.key_path = os.path.join(folder, "logins.key")
        # protect: (schützen, entsperren) – Standard: DPAPI unter Windows, sonst unverändert (Dateirechte)
        if protect is None:
            if os.name == "nt":
                protect = (lambda k: _dpapi(k, True), lambda k: _dpapi(k, False))
            else:
                protect = (lambda k: k, lambda k: k)
        self._protect, self._unprotect = protect
        self._key = None
        self._data = None

    # -- Schlüssel ---------------------------------------------------------------
    def _load_key(self):
        if self._key is not None:
            return self._key
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                key = self._unprotect(f.read())
            if len(key) != 32:
                raise StoreError("Schlüssel ungültig")
        else:
            key = secrets.token_bytes(32)                 # AES-256
            os.makedirs(self.folder, exist_ok=True)
            blob = self._protect(key)
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(blob)
        self._key = key
        return key

    # -- Lesen/Schreiben ---------------------------------------------------------
    def _aes(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(self._load_key())

    def _read(self):
        if self._data is not None:
            return self._data
        if not os.path.exists(self.data_path):
            self._data = {}
            return self._data
        with open(self.data_path, "rb") as f:
            raw = f.read()
        if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + NONCE_SIZE + 16:
            raise StoreError("Datei mit den Anmeldungen ist beschädigt")
        nonce = raw[len(MAGIC):len(MAGIC) + NONCE_SIZE]
        try:
            plain = self._aes().decrypt(nonce, raw[len(MAGIC) + NONCE_SIZE:], MAGIC)
        except Exception:
            raise StoreError("Anmeldungen lassen sich nicht entschlüsseln (anderer PC/Benutzer oder Datei "
                             "verändert) – bitte neu anmelden") from None
        self._data = json.loads(plain.decode("utf-8"))
        return self._data

    def _write(self):
        nonce = secrets.token_bytes(NONCE_SIZE)
        plain = json.dumps(self._data, ensure_ascii=False).encode("utf-8")
        blob = MAGIC + nonce + self._aes().encrypt(nonce, plain, MAGIC)
        os.makedirs(self.folder, exist_ok=True)
        tmp = self.data_path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        os.replace(tmp, self.data_path)

    # -- Schnittstelle -----------------------------------------------------------
    def logins(self):
        """{Quelle: {"gespeichert": Zeit, "cookies": Anzahl, "domains": [...]}} – ohne Cookie-Inhalte."""
        try:
            data = self._read()
        except StoreError:
            return {}
        return {sid: {"gespeichert": entry.get("saved", 0), "cookies": len(entry.get("cookies", [])),
                      "domains": sorted({c.get("domain", "").lstrip(".") for c in entry.get("cookies", [])})}
                for sid, entry in data.items()}

    def cookies(self, source_id):
        """Cookies einer Quelle (Liste von Dicts: name, value, domain, path, secure, expires)."""
        entry = self._read().get(source_id) or {}
        now = time.time()
        return [c for c in entry.get("cookies", []) if not c.get("expires") or c["expires"] > now]

    def all_cookies(self):
        """Alle gespeicherten Cookies (für den eingebauten Browser)."""
        now = time.time()
        return [c for entry in self._read().values() for c in entry.get("cookies", [])
                if not c.get("expires") or c["expires"] > now]

    def save(self, source_id, cookies):
        data = self._read()
        data[source_id] = {"saved": time.time(), "cookies": list(cookies)}
        self._write()

    def forget(self, source_id=None):
        """Anmeldung einer Quelle löschen (None = alle)."""
        data = self._read()
        if source_id is None:
            data.clear()
        else:
            data.pop(source_id, None)
        self._write()


def cookie_header(cookies, url):
    """Cookie-Kopfzeile für url aus einer Cookie-Liste (Domain, Pfad und secure werden beachtet)."""
    from urllib.parse import urlparse
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    pairs = []
    for c in cookies:
        domain = (c.get("domain") or "").lower()
        bare = domain.lstrip(".")
        if not bare or not (host == bare or host.endswith("." + bare)):
            continue
        if c.get("secure") and parts.scheme != "https":
            continue
        if not path.startswith(c.get("path") or "/"):
            continue
        pairs.append(f"{c['name']}={c['value']}")
    return "; ".join(pairs)
