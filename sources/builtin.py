# Modul: sources/builtin.py
# Funktion: Mitgelieferte Quellen. Echte Trefferlisten (sites.py): TSR, CurseForge, ModTheSims, Sims Finds,
#           Tumblr, Sims 4 Updates, The Sims Catalog, NewSea sowie mit Anmeldung LoversLab und SexySims.
#           Patreon (Suche findet nur Creator), Simsworkshop (Captcha-Schleife), Around the Sims (keine Suche)
#           und Google bleiben Such-Links für den eingebauten Browser.

from .base import LinkSource
from .sites import (CurseForge, LoversLab, ModTheSims, NewSea, SexySims, Sims4Updates, SimsFinds, TheSimsCatalog,
                    TheSimsResource, Tumblr)


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
        LoversLab(),
        SexySims(),
        # Simsworkshop zeigt vor der Suche eine Cloudflare-Prüfung („Ich bin ein Mensch“), die auch von Hand in einer
        # Schleife hängen bleibt – deshalb nur als Such-Link
        LinkSource("simsworkshop", "Simsworkshop", "https://www.simsworkshop.net/search/?q={query}&t=resource",
                   homepage="https://www.simsworkshop.net", login_url="https://www.simsworkshop.net/login/"),
        # Around the Sims hat keine eigene Suche
        LinkSource("aroundthesims", "Around the Sims",
                   "https://www.google.com/search?q=site%3Asims4.aroundthesims3.com+{query}",
                   homepage="https://sims4.aroundthesims3.com"),
        LinkSource("google", "Google", "https://www.google.com/search?q=sims+4+{query}",
                   homepage="https://www.google.com"),
    ]
