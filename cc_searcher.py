# Modul: cc_searcher.py
# Funktion: Sucht nach fehlenden CC- oder Mod-Dateien online (TSR, CurseForge, ModTheSims etc.)
#
# Aktueller Stand:
# - Erzeugt Suchlinks aus Dateinamen; ein Klick im Report öffnet die Suche im Browser.
# - Die Seiten werden noch nicht automatisch abgefragt: TSR, CurseForge, Patreon & Co.
#   blocken einfache Skript-Anfragen (Cloudflare) oder brauchen JavaScript/Login.
#   Dafür ist die Advanced-Version unten geplant.
#
# Aufgaben:
# - Automatische Suche basierend auf Dateinamen oder CC-IDs
# - Nutzung von Web Scraping (Requests + BeautifulSoup)
# - Trefferlisten mit Links zur Suchanfrage sammeln
# - Unterstützung fester Quellen:
#   - The Sims Resource (TSR)
#   - CurseForge
#   - ModTheSims
#   - Tumblr
#   - Patreon
#   - LoversLab
#   - SexySims
#   - NewSea
#
# Erweiterte Architektur (geplant):
# - Feste Quellen werden als Core-Module direkt eingebunden (kein Plugin erforderlich für Haupt-Sites)
# - Erweiterbare Plugin-Architektur für zusätzliche, benutzerdefinierte Quellen
# - Modularer Aufbau:
#   - cc_searcher/core_sites/ (alle großen Seiten wie TSR, CurseForge, MTS, etc.)
#   - cc_searcher/plugins/ (zusätzliche Quellen als Plugins)
#   - cc_searcher/login_manager.py (Login- und Session-Management inkl. 2FA Support)
#   - cc_searcher/captcha_solver.py (Manuelle oder automatische Captcha-Behandlung)
#
# Zukünftige Erweiterungen (Advanced-Version geplant):
# - Vollständiges HTML-Parsing für echte Trefferlisten (Titel, Bild, Downloadlink, Beschreibung)
# - Headless Browser Support (Selenium/Playwright)
# - Unterstützung für Login und Authentifizierung:
#   - Sichtbares Login-Fenster
#   - Benutzer loggt sich selbst ein (mit 2FA-Support)
#   - Cookies werden automatisch gespeichert und **mit AES256 verschlüsselt**
#   - Entschlüsselung nur zur Laufzeit im RAM (keine Klartext-Cookies auf Disk)
# - Manuelle Captcha-Lösung: Fenster öffnet sich, Benutzer löst Captcha manuell
# - (Optional: Captcha-Automatisierung via Services, falls gewünscht)
# - Automatisiertes Download-Management
#
# Strukturvorschlag:
# - Funktion: search_alternatives(missing_cc_list) → Gibt Trefferliste zurück
#   (aktuell: {Name: {Seite: Such-URL}})

import os
import re
from urllib.parse import quote_plus

SEARCH_ENGINES = {
    "The Sims Resource": "https://www.thesimsresource.com/search/{query}/",
    "CurseForge": "https://www.curseforge.com/sims4/search?search={query}",
    "ModTheSims": "https://modthesims.info/browse.php?tag={query}",
    "Tumblr": "https://www.tumblr.com/search/{query}",
    "Patreon": "https://www.patreon.com/search?q={query}",
    "LoversLab": "https://www.loverslab.com/search/?q={query}",
    "SexySims": "https://sexysims.info/browse.php?tag={query}",
    # Die alte URL (sims3-search.php) durchsucht Sims-3-Inhalte; eine Sims-4-Such-URL ist nicht
    # bekannt (die Seite blockt automatische Abrufe), daher Google-Suche direkt auf newseasims.com
    "NewSea": "https://www.google.com/search?q=site%3Anewseasims.com+sims+4+{query}",
    "Google": "https://www.google.com/search?q=sims+4+{query}",
}


def query_from_filename(filename):
    """Macht aus einem Dateinamen einen brauchbaren Suchbegriff.
    "[Creator] Cool_Hair-v2 (Merged).package" -> "Creator Cool Hair v2"."""
    name = os.path.splitext(os.path.basename(filename))[0]
    name = re.sub(r"\((merged|merge|copy|kopie)\)", " ", name, flags=re.I)
    name = re.sub(r"[_\-\.\[\]\(\)!]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def search_links(name):
    """Gibt {Seitenname: Such-URL} für einen Dateinamen oder Suchbegriff zurück."""
    query = quote_plus(query_from_filename(name))
    return {site: url.format(query=query) for site, url in SEARCH_ENGINES.items()}


def search_alternatives(names):
    """Gibt {Name: {Seitenname: Such-URL}} für mehrere Namen zurück."""
    return {name: search_links(name) for name in names}
