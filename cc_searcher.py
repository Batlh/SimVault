# Modul: cc_searcher.py
# Funktion: Sucht nach fehlenden CC- oder Mod-Dateien online (TSR, CurseForge, ModTheSims etc.)
#
# Aktueller Stand:
# - Die Quellen kommen aus dem Paket "sources" (mitgelieferte Quellen + Erweiterungen aus dem
#   Ordner "plugins", siehe plugins/README.md). Neue Webseiten lassen sich dort ergänzen.
# - Erzeugt Suchlinks aus Dateinamen; ein Klick im Report öffnet die Suche im Browser.
# - TSR, CurseForge, Patreon & Co. blocken einfache Skript-Anfragen (Cloudflare) oder brauchen JavaScript/Login.
#   Umgesetzt (Seite „Websuche“): eingebauter Browser (Qt WebEngine) mit Anmeldung, verschlüsselten Cookies
#   (secure_store.py), Download-Verwaltung (downloads.py) und session.render() für Voll-Quellen.
#   Offen: die Treffer-Parser für die großen Seiten selbst (als Voll-Quellen).
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

from sources import enabled_sources
from sources.builtin import builtin_sources

# Für ältere Aufrufer: {Seitenname: URL-Vorlage} der mitgelieferten Quellen
SEARCH_ENGINES = {s.name: s.template for s in builtin_sources()}


def query_from_filename(filename):
    """Macht aus einem Dateinamen einen brauchbaren Suchbegriff.
    "[Creator] Cool_Hair-v2 (Merged).package" -> "Creator Cool Hair v2"."""
    name = os.path.splitext(os.path.basename(filename))[0]
    name = re.sub(r"\((merged|merge|copy|kopie)\)", " ", name, flags=re.I)
    name = re.sub(r"[_\-\.\[\]\(\)!]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def search_links(name, cfg=None):
    """Gibt {Quellenname: Such-URL} für einen Dateinamen oder Suchbegriff zurück (aktive Quellen)."""
    query = query_from_filename(name)
    links = {}
    for source in enabled_sources(cfg):
        url = source.search_url(query)
        if url:
            links[source.name] = url
    return links


def search_alternatives(names, cfg=None):
    """Gibt {Name: {Quellenname: Such-URL}} für mehrere Namen zurück."""
    return {name: search_links(name, cfg) for name in names}
