# Modul: cc_searcher.py
# Funktion: Erzeugt Suchlinks, um CC auf den bekannten Seiten wiederzufinden
#           (z. B. für defekte Dateien oder um eine neuere Version zu suchen).
#
# Die Seiten werden bewusst nicht automatisch abgefragt: TSR, CurseForge, Patreon & Co.
# blocken einfache Skript-Anfragen (Cloudflare) oder brauchen JavaScript/Login.
# Ein Klick auf den Link im Report öffnet die Suche direkt im Browser.
#
# Später möglich: echte Trefferlisten über einen Browser (Playwright) mit manuellem Login.

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
