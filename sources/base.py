# Modul: sources/base.py
# Funktion: Grundlage für CC-Quellen (Webseiten wie TSR, CurseForge, Patreon …).
#
# Eine Quelle ist eine Klasse, die von Source erbt. Es gibt zwei Ausbaustufen:
#   1. Link-Quelle:  liefert nur eine Such-URL (search_url) – ein Klick öffnet die Suche im Browser.
#                    Dafür reicht auch eine einfache .json-Datei im Erweiterungs-Ordner (siehe loader.py).
#   2. Voll-Quelle:  überschreibt search() und liefert echte Treffer (Titel, Bild, Link, Ersteller …).
#                    Kann ein Login verlangen (needs_login/login_url) – das Programm öffnet dann ein
#                    sichtbares Login-Fenster, der Nutzer meldet sich selbst an (inkl. 2FA/Captcha),
#                    und die Cookies werden der Quelle über `session` zur Verfügung gestellt.
#
# Erweiterungen (Plugins) sind ganz normale Python-Dateien mit solchen Klassen oder .json-Dateien,
# die in den Erweiterungs-Ordner gelegt werden. Siehe plugins/README.md.

from dataclasses import dataclass, field
from urllib.parse import quote_plus

# Wird erhöht, wenn sich die Schnittstelle für Erweiterungen inkompatibel ändert.
API_VERSION = 1


@dataclass
class SearchResult:
    """Ein Treffer einer Quelle."""
    title: str
    url: str
    source_id: str = ""
    image_url: str = ""
    creator: str = ""
    description: str = ""
    download_url: str = ""
    extra: dict = field(default_factory=dict)


class Source:
    """Basisklasse aller Quellen. Unterklassen setzen mindestens id und name."""

    id = ""                  # eindeutig, klein, ohne Leerzeichen, z. B. "tsr"
    name = ""                # Anzeigename, z. B. "The Sims Resource"
    homepage = ""
    description = ""
    adult = False            # Inhalte nur für Erwachsene – in der Oberfläche gekennzeichnet
    needs_login = False      # Suche/Download nur mit Anmeldung
    login_url = ""           # Seite, auf der man sich anmeldet
    enabled_by_default = True
    origin = "mitgeliefert"  # wird vom Lader gesetzt: "mitgeliefert" oder Pfad der Erweiterung

    def search_url(self, query):
        """URL, die die Suche nach query im Browser öffnet (oder None)."""
        return None

    def search(self, query, session=None):
        """Echte Treffer als Liste von SearchResult. Link-Quellen liefern nichts."""
        return []

    @property
    def can_search(self):
        """True, wenn die Quelle echte Treffer liefern kann (search() überschrieben)."""
        return type(self).search is not Source.search

    def __repr__(self):
        return f"<Quelle {self.id}: {self.name}>"


class LinkSource(Source):
    """Quelle, die nur eine Such-URL kennt. template enthält {query}."""

    template = ""

    def __init__(self, id=None, name=None, template=None, homepage=None, description=None,
                 adult=None, needs_login=None, login_url=None, enabled_by_default=None):
        for key, value in (("id", id), ("name", name), ("template", template), ("homepage", homepage),
                           ("description", description), ("adult", adult), ("needs_login", needs_login),
                           ("login_url", login_url), ("enabled_by_default", enabled_by_default)):
            if value is not None:
                setattr(self, key, value)

    def search_url(self, query):
        if not self.template:
            return None
        return self.template.replace("{query}", quote_plus(query))
