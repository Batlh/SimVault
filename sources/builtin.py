# Modul: sources/builtin.py
# Funktion: Mitgelieferte Quellen. TSR, CurseForge und ModTheSims liefern echte Trefferlisten
#           (sites.py); die übrigen Seiten brauchen eine Anmeldung oder JavaScript-Suche und bleiben
#           Such-Links, die sich im eingebauten Browser öffnen.

from .base import LinkSource
from .sites import CurseForge, ModTheSims, TheSimsResource


def builtin_sources():
    return [
        TheSimsResource(),
        CurseForge(),
        ModTheSims(),
        LinkSource("tumblr", "Tumblr", "https://www.tumblr.com/search/{query}", homepage="https://www.tumblr.com"),
        LinkSource("patreon", "Patreon", "https://www.patreon.com/search?q={query}",
                   homepage="https://www.patreon.com", login_url="https://www.patreon.com/login"),
        LinkSource("loverslab", "LoversLab", "https://www.loverslab.com/search/?q={query}",
                   homepage="https://www.loverslab.com", adult=True, needs_login=True,
                   login_url="https://www.loverslab.com/login/"),
        LinkSource("sexysims", "SexySims", "https://sexysims.info/browse.php?tag={query}",
                   homepage="https://sexysims.info", adult=True),
        # Die alte URL (sims3-search.php) durchsucht Sims-3-Inhalte; eine Sims-4-Such-URL ist nicht
        # bekannt (die Seite blockt automatische Abrufe), daher Google-Suche direkt auf newseasims.com
        LinkSource("newsea", "NewSea", "https://www.google.com/search?q=site%3Anewseasims.com+sims+4+{query}",
                   homepage="http://www.newseasims.com"),
        LinkSource("google", "Google", "https://www.google.com/search?q=sims+4+{query}",
                   homepage="https://www.google.com"),
    ]
