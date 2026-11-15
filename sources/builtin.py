# Modul: sources/builtin.py
# Funktion: Mitgelieferte Quellen. TSR, CurseForge, ModTheSims, Sims Finds, Tumblr, Sims 4 Updates und
#           The Sims Catalog und NewSea liefern echte Trefferlisten (sites.py); die übrigen Seiten brauchen eine Anmeldung,
#           haben eine Captcha-Prüfung oder keine Suche und bleiben Such-Links für den eingebauten Browser.

from .base import LinkSource
from .sites import (CurseForge, ModTheSims, NewSea, Sims4Updates, SimsFinds, TheSimsCatalog, TheSimsResource,
                    Tumblr)


def builtin_sources():
    return [
        TheSimsResource(),
        CurseForge(),
        ModTheSims(),
        SimsFinds(),
        Tumblr(),
        Sims4Updates(),
        TheSimsCatalog(),
        NewSea(),
        LinkSource("patreon", "Patreon", "https://www.patreon.com/search?q={query}",
                   homepage="https://www.patreon.com", login_url="https://www.patreon.com/login"),
        LinkSource("loverslab", "LoversLab", "https://www.loverslab.com/search/?q={query}",
                   homepage="https://www.loverslab.com", adult=True, needs_login=True,
                   login_url="https://www.loverslab.com/login/"),
        LinkSource("sexysims", "SexySims", "https://sexysims.info/browse.php?tag={query}",
                   homepage="https://sexysims.info", adult=True, needs_login=True,
                   login_url="https://sexysims.info/login.php"),
        # Simsworkshop zeigt vor der Suche eine Cloudflare-Prüfung („Ich bin ein Mensch“) – die löst man selbst
        # im eingebauten Browser, deshalb nur als Such-Link
        LinkSource("simsworkshop", "Simsworkshop", "https://www.simsworkshop.net/search/?q={query}&t=resource",
                   homepage="https://www.simsworkshop.net", login_url="https://www.simsworkshop.net/login/"),
        # Around the Sims hat keine eigene Suche
        LinkSource("aroundthesims", "Around the Sims",
                   "https://www.google.com/search?q=site%3Asims4.aroundthesims3.com+{query}",
                   homepage="https://sims4.aroundthesims3.com"),
        LinkSource("google", "Google", "https://www.google.com/search?q=sims+4+{query}",
                   homepage="https://www.google.com"),
    ]
