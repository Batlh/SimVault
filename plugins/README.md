# SimVault-Erweiterungen für Quellen

Hier kannst du weitere Webseiten (Quellen) für die CC-Suche ergänzen. SimVault lädt Erweiterungen aus:

- diesem Ordner `plugins` (neben dem Programm bzw. im SimVault-Ordner),
- deinem Benutzerordner: `%APPDATA%\SimVault\plugins` (Windows),
- weiteren Ordnern aus `config.json` → `"plugin_folders": ["D:\\Meine Quellen"]`.

Dateien, die mit `_` beginnen, werden ignoriert (so sind die Beispiele hier ausgeschaltet).
Im Programm unter **Quellen** siehst du alle geladenen Quellen, kannst sie an-/ausschalten und
nach dem Ergänzen auf **Neu laden** klicken. Fehler in einer Erweiterung werden dort angezeigt.

## 1. Einfache Quelle – nur eine `.json`-Datei, ohne Programmieren

Eine Quelle, bei der ein Klick die Suche im Browser öffnet. `{query}` wird durch den Suchbegriff ersetzt:

```json
{
  "id": "simsdom",
  "name": "SimsDom",
  "search_url": "https://simsdom.com/search?q={query}",
  "homepage": "https://simsdom.com",
  "adult": false,
  "needs_login": false,
  "enabled": true
}
```

Mehrere Quellen in einer Datei: einfach eine Liste `[ {...}, {...} ]`.
Beispiel: [`_beispiel_linkquelle.json`](_beispiel_linkquelle.json) – zum Aktivieren den `_` entfernen
(die Such-URLs dort sind Muster – vorher kurz im Browser prüfen).

## 2. Volle Quelle – eine `.py`-Datei mit echten Treffern

Eine Klasse, die von `Source` erbt und `search()` überschreibt. Sie liefert `SearchResult`-Objekte
(Titel, Link, Vorschaubild, Ersteller, Beschreibung, Download-Link). Braucht die Seite eine Anmeldung,
setzt du `needs_login = True` und `login_url` – SimVault öffnet dann ein sichtbares Login-Fenster,
du meldest dich selbst an (auch mit 2FA/Captcha), und die Anmeldung wird über `session` weitergegeben.

```python
from sources.base import Source, SearchResult

REQUIRES_API = 1


class MeineQuelle(Source):
    id = "meinequelle"
    name = "Meine Quelle"
    homepage = "https://example.com"

    def search_url(self, query):
        return "https://example.com/search?q=" + query

    def search(self, query, session=None):
        # Seite abrufen, Treffer auslesen …
        return [SearchResult(title="Beispiel", url="https://example.com/cc/1", source_id=self.id)]
```

Beispiel mit Erklärungen: [`_beispiel_vollquelle.py`](_beispiel_vollquelle.py).

Eine Erweiterung mit derselben `id` wie eine mitgelieferte Quelle ersetzt diese – so lässt sich
auch eine veraltete Such-URL selbst korrigieren.
