# Modul: sources/sites.py
# Funktion: Echte Trefferlisten für die großen CC-Seiten (Voll-Quellen).
#
# Aufbau der Seiten (im Browser geprüft, Stand November 2026):
# - The Sims Resource: Suche /downloads/browse/category/sims4/search/<Begriffe>/ – je Treffer ein
#   <div class="item-wrapper" data-item="{…JSON…}"> mit Titel, Ersteller, Beschreibung, ID; Bild als
#   background-url im Link. Download nur über die Seite (Wartezeit / VIP) -> eingebauter Browser.
# - CurseForge: /sims4/search?search=<Begriffe> – je Treffer <div class="project-card"> mit Bild, Name,
#   Ersteller, Beschreibung und Download-Seite (Countdown, startet den Download selbst) -> Browser.
# - ModTheSims: Suche nur nach Schlagwort (/downloads.php?gs=4&tag=…) oder Ersteller (&creator=…);
#   je Treffer <li class="smol-card-component">. Die Detailseite enthält direkte Datei-Links
#   (getfile.php), die SimVault selbst herunterladen kann.
# Ändert eine Seite ihren Aufbau, liefert die Quelle einfach keine Treffer – der Such-Link funktioniert weiter.
#
# Geladen wird zuerst normal (session.get). Blockt die Seite das (Cloudflare & Co.) und läuft das
# Programmfenster, holt der eingebaute Browser die Seite (session.render).

import re
import json
import html as htmlmod
import logging
from urllib.parse import quote, quote_plus, urljoin

from .base import SearchResult, Source

log = logging.getLogger(__name__)

MAX_RESULTS = 30
BLOCKED_MARKERS = ("cf-challenge", "challenge-platform", "Just a moment...", "Attention Required!",
                   "cf_chl_opt", "Checking your browser")


def text(fragment):
    """Text aus einem HTML-Stück: Tags weg, Entities auflösen, Leerraum zusammenfassen."""
    fragment = re.sub(r"<br\s*/?>", " ", fragment or "", flags=re.I)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", htmlmod.unescape(fragment)).strip()


def first(pattern, chunk, flags=re.S | re.I):
    """Erste Fundstelle. Im Muster steht Q für ein beliebiges Anführungszeichen (' oder "),
    V für einen Attributwert ohne Anführungszeichen – Seiten mischen beides."""
    pattern = pattern.replace("Q", "[\"']").replace("V", "[^\"']*")
    m = re.search(pattern, chunk, flags)
    return m.group(1) if m else ""


def fetch(session, url):
    """Seite laden – normal, bei Blockade über den eingebauten Browser."""
    page = ""
    try:
        page = session.get(url)
    except Exception as e:                      # z. B. HTTP 403 von Cloudflare
        log.info("%s normal nicht ladbar (%s) – versuche den eingebauten Browser", url, e)
    if not page or any(m in page[:20000] for m in BLOCKED_MARKERS):
        renderer = getattr(session, "renderer", None)
        if renderer:
            page = session.render(url)
        elif not page:
            raise OSError("Seite blockt einfache Abrufe – im Programmfenster suchen (eingebauter Browser)")
    return page


class TheSimsResource(Source):
    id = "tsr"
    name = "The Sims Resource"
    homepage = "https://www.thesimsresource.com"
    login_url = "https://www.thesimsresource.com/account/login"
    description = "Größte CC-Seite. Treffer mit Bild; heruntergeladen wird im eingebauten Browser (Wartezeit)."
    base = "https://www.thesimsresource.com"

    def search_url(self, query):
        return f"{self.base}/downloads/browse/category/sims4/search/{quote(query.strip())}/"

    def search(self, query, session=None):
        return self.parse(fetch(session, self.search_url(query)))

    def parse(self, page):
        results = []
        parts = re.split(r'(?=<div class=["\']item-wrapper)', page)
        for chunk in parts[1:MAX_RESULTS + 1]:
            raw = first(r'data-item="([^"]*)"', chunk) or first(r"data-item='([^']*)'", chunk)
            try:
                data = json.loads(htmlmod.unescape(raw)) if raw else {}
            except ValueError:
                data = {}
            href = first(r'<a(?=[^>]*item-link)[^>]*href=Q(V)Q', chunk) or first(r'href=Q(/downloads/details/V)Q', chunk)
            if not href:
                continue
            slug = first(r"/title/([^/]+)/", href)
            title = data.get("title") or htmlmod.unescape(slug.replace("-", " ")).strip().title()
            image = first(r"background(?:-image)?:\s*url\(['\"]?([^'\")]+)", chunk)
            results.append(SearchResult(
                title=title or "TSR " + data.get("ID", ""), url=urljoin(self.base, href), source_id=self.id,
                image_url=urljoin(self.base, image) if image else "", creator=data.get("creator", ""),
                description=(data.get("description") or "")[:400],
                # Der Download-Knopf der Detailseite startet per Skript (mit Wartezeit ohne VIP) –
                # dafür wird die Detailseite im eingebauten Browser geöffnet
                extra={"kostenlos": data.get("free") == "1", "id": data.get("ID", "")}))
        return results


    def download_urls(self, result, session=None):
        return []


class CurseForge(Source):
    id = "curseforge"
    name = "CurseForge"
    homepage = "https://www.curseforge.com/sims4"
    description = "Offizielle Mod-Plattform. Treffer mit Bild; der Download startet im eingebauten Browser."
    base = "https://www.curseforge.com"

    def search_url(self, query):
        return f"{self.base}/sims4/search?search={quote_plus(query.strip())}"

    def search(self, query, session=None):
        return self.parse(fetch(session, self.search_url(query)))

    def parse(self, page):
        results = []
        for chunk in re.split(r'(?=<div class=["\']\s*project-card)', page)[1:MAX_RESULTS + 1]:
            href = first(r'<a(?=[^>]*class=QnameQ)[^>]*href=Q(V)Q', chunk)
            if not href:
                continue
            title = text(first(r'<a(?=[^>]*class=QnameQ)[^>]*>(.*?)</a>', chunk))
            download = first(r'<a(?=[^>]*download-cta)[^>]*href=Q(V)Q', chunk) or first(r'href=Q(V/download/\d+)Q', chunk)
            results.append(SearchResult(
                title=title, url=urljoin(self.base, href), source_id=self.id,
                image_url=first(r'<img[^>]+src=Q(V)Q', chunk),
                creator=text(first(r'class=Qauthor-nameVQ[^>]*>(.*?)</a>', chunk)),
                description=text(first(r'<p class=QdescriptionQ[^>]*>(.*?)</p>', chunk)),
                # Download-Seite: Countdown, dann startet der Download – das übernimmt der eingebaute Browser
                extra={"download_seite": urljoin(self.base, download) if download else ""}))
        return results

    def download_urls(self, result, session=None):
        return []


class ModTheSims(Source):
    id = "modthesims"
    name = "ModTheSims"
    homepage = "https://modthesims.info"
    login_url = "https://modthesims.info/login.php"
    description = "Sucht nach Schlagwort und Ersteller. Dateien lädt SimVault direkt herunter."
    base = "https://modthesims.info"

    def search_url(self, query):
        return f"{self.base}/downloads.php?gs=4&tag={quote_plus(query.strip())}"

    def _queries(self, query):
        """ModTheSims sucht nur ein Schlagwort oder einen Ersteller: der ganze Begriff, dann
        erstes Wort als Ersteller, dann die einzelnen Wörter."""
        words = [w for w in re.split(r"\s+", query.strip()) if w]
        urls = [self.search_url(query)]
        if len(words) > 1:
            urls.append(f"{self.base}/downloads.php?gs=4&creator={quote_plus(words[0])}"
                        f"&tag={quote_plus(' '.join(words[1:]))}")
            urls.append(f"{self.base}/downloads.php?gs=4&creator={quote_plus(words[0])}")
            urls += [self.search_url(w) for w in words if len(w) >= 4]
        return urls

    def search(self, query, session=None):
        seen, results = set(), []
        for url in self._queries(query):
            for r in self.parse(fetch(session, url)):
                if r.url not in seen:
                    seen.add(r.url)
                    results.append(r)
            if len(results) >= 10:
                break
        return results[:MAX_RESULTS]

    def parse(self, page):
        results = []
        for chunk in re.split(r'(?=<li[^>]*class=["\']smol-card-component)', page)[1:MAX_RESULTS + 1]:
            href = first(r'class=QdownloadtitleVQ[^>]*>\s*<a [^>]*href=Q(V)Q', chunk)
            if not href:
                continue
            image = first(r'<img(?=[^>]*featuredimage)[^>]*src=Q(V)Q', chunk)
            if image.startswith("//"):
                image = "https:" + image
            preview = first(r'class=QdownloadPreviewQ[^>]*>(.*?)(?:<a [^>]*>more|</p>)', chunk)
            results.append(SearchResult(
                title=text(first(r'class=QdownloadtitleVQ[^>]*>\s*<a [^>]*>(.*?)</a>', chunk)),
                url=urljoin(self.base, href), source_id=self.id, image_url=image,
                creator=text(first(r'class=QdownloadcreatornameQ[^>]*>.*?<a [^>]*>(.*?)</a>', chunk)),
                description=text(preview)[:400]))
        return results

    def download_urls(self, result, session=None):
        """Alle Dateien eines Downloads (getfile.php-Links der Detailseite)."""
        page = fetch(session, result.url)
        urls = []
        for link in re.findall(r'<a [^>]*class=["\']downloadlink[^>]*href=["\']([^"\']*getfile\.php[^"\']*)', page):
            link = htmlmod.unescape(link)
            if link not in urls:
                urls.append(link)
        return urls
