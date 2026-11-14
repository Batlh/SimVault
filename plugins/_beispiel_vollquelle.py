# Beispiel für eine Voll-Quelle (Erweiterung) – zum Aktivieren den Unterstrich im Dateinamen entfernen.
#
# Eine Voll-Quelle liefert echte Treffer statt nur einer Such-URL. Ablauf:
#   1. SimVault ruft search(query, session) auf – query ist z. B. der Name einer fehlenden CC.
#   2. Die Quelle lädt die Suchseite (mit session, falls eine Anmeldung nötig ist) und liest die Treffer aus.
#   3. Sie gibt eine Liste von SearchResult zurück; SimVault zeigt sie mit Vorschaubild an.
#
# session: ein Objekt mit get(url) -> Text. SimVault stellt es bereit; bei needs_login = True enthält
#          es die Cookies aus dem Login-Fenster. Ohne Login reicht urllib (siehe unten).

import re
import urllib.request
from urllib.parse import quote_plus

from sources.base import Source, SearchResult

REQUIRES_API = 1


class BeispielQuelle(Source):
    id = "beispiel"
    name = "Beispiel-Quelle"
    homepage = "https://example.com"
    description = "Zeigt, wie eine Voll-Quelle aufgebaut ist."
    needs_login = False
    login_url = ""

    def search_url(self, query):
        return f"https://example.com/search?q={quote_plus(query)}"

    def _get(self, url, session):
        if session is not None:
            return session.get(url)
        request = urllib.request.Request(url, headers={"User-Agent": "SimVault"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", "replace")

    def search(self, query, session=None):
        html = self._get(self.search_url(query), session)
        results = []
        # Hier die Treffer aus dem HTML der Seite herauslesen – das Muster ist nur ein Beispiel.
        for url, title in re.findall(r'<a class="result" href="([^"]+)">([^<]+)</a>', html):
            results.append(SearchResult(title=title.strip(), url=url, source_id=self.id))
        return results
