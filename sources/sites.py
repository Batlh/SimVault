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


def _split_words(query):
    return [w for w in re.split(r"[\s_\-]+", query.strip()) if w]


class SimsFinds(Source):
    """Sims Finds: Suche als /results/sims4-<begriffe> (Wörter mit Bindestrich). Die CSS-Klassen der Seite sind
    verschlüsselt – gelesen wird über die schema.org-Angaben (itemprop name/url/image), die bleiben stabil.
    Mehrere Wörter finden dort oft nichts, deshalb danach die einzelnen Wörter."""
    id = "simsfinds"
    name = "Sims Finds"
    homepage = "https://www.simsfinds.com"
    description = "Große CC-Sammlung. Treffer mit Bild; heruntergeladen wird im eingebauten Browser (Wartezeit)."
    base = "https://www.simsfinds.com"

    def search_url(self, query):
        slug = "-".join(re.sub(r"[^a-z0-9]+", "", w.lower()) for w in _split_words(query))
        return f"{self.base}/results/sims4-{slug}" if slug else ""

    def search(self, query, session=None):
        words = _split_words(query)
        urls = [self.search_url(query)] + ([self.search_url(w) for w in words if len(w) >= 4] if len(words) > 1 else [])
        seen, results = set(), []
        for url in urls:
            for r in self.parse(fetch(session, url)):
                if r.url not in seen:
                    seen.add(r.url)
                    results.append(r)
            if len(results) >= 10:
                break
        return results[:MAX_RESULTS]

    def parse(self, page):
        results = []
        for chunk in re.split(r'(?=<div[^>]*itemprop=["\']itemListElement)', page)[1:MAX_RESULTS + 1]:
            href = first(r'<a[^>]*href=Q(V/downloads/\d+/V)Q', chunk)
            if not href:
                continue
            title = text(first(r'itemprop=QnameQ[^>]*>(.*?)</', chunk)) or text(first(r'<a[^>]*title=Q(V)Q', chunk))
            results.append(SearchResult(
                title=title, url=urljoin(self.base, href), source_id=self.id,
                image_url=first(r'<img[^>]*src=Q(https?://V)Q', chunk),
                creator=text(first(r"\bby ([^<]{2,40})$", title)),
                description=" ".join(text(t) for t in re.findall(r'data-type=["\']hashtag[^>]*>([^<]+)<', chunk, re.I)) or ""))
        return results

    def download_urls(self, result, session=None):
        return []                                   # Download-Knopf mit Wartezeit -> eingebauter Browser


class WordPressSite(Source):
    """CC-Seiten auf WordPress (?s=Suche). Versteht die üblichen Vorlagen: <article> mit entry-title
    (Sims 4 Updates und viele Blogs) und Listen mit post-title / wp-post-image (The Sims Catalog)."""
    base = ""
    search_path = "/"

    def search_url(self, query):
        return f"{self.base}{self.search_path}?s={quote_plus(query.strip())}"

    def search(self, query, session=None):
        results = self.parse(fetch(session, self.search_url(query)))
        words = _split_words(query)
        if not results and len(words) > 1:          # WordPress sucht mit UND – ohne Treffer: längstes Wort
            results = self.parse(fetch(session, self.search_url(max(words, key=len))))
        return results

    def parse(self, page):
        results = []
        chunks = re.split(r'(?=<article\b|<div[^>]*class=["\'][^"\']*post-single-col-grid)', page)[1:]
        for chunk in chunks[:MAX_RESULTS]:
            href = first(r'class=Q(?:entry-title|post-title)VQ[^>]*>\s*<a[^>]*href=Q(V)Q', chunk) or \
                first(r'<a[^>]*class=Qentry-title-linkQ[^>]*href=Q(V)Q', chunk)
            if not href:
                continue
            title = text(first(r'class=Q(?:entry-title|post-title)VQ[^>]*>\s*<a[^>]*>(.*?)</a>', chunk))
            image = first(r'<img[^>]*data-src=Q(https?://V)Q', chunk) or \
                first(r'<img(?=[^>]*(?:wp-post-image|entry-image|post-image))[^>]*src=Q(https?://V)Q', chunk)
            creator = text(first(r'rel=QauthorQ[^>]*>(.*?)</a>', chunk)) or \
                text(first(r"\bby ([^<]{2,40}?)(?: at [^<]{2,30})?$", title))
            paragraphs = [text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.S | re.I)]
            description = next((p for p in paragraphs if p and not p.startswith(("Filed Under", "Tagged", "Posted"))), "")
            results.append(SearchResult(title=title, url=urljoin(self.base, href), source_id=self.id,
                                        image_url=image, creator=creator, description=description[:300]))
        return results

    def download_urls(self, result, session=None):
        return []                                   # Beiträge verlinken auf die Originalseite -> Browser


class Sims4Updates(WordPressSite):
    id = "sims4updates"
    name = "Sims 4 Updates"
    homepage = "https://sims4updates.net"
    description = "Sammelt CC von vielen Seiten (TSR, Tumblr, Patreon …) – verlinkt auf das Original."
    base = "https://sims4updates.net"


class TheSimsCatalog(WordPressSite):
    id = "simscatalog"
    name = "The Sims Catalog"
    homepage = "https://thesimscatalog.com/sims4/"
    description = "CC-Katalog mit Links zur Originalseite."
    base = "https://thesimscatalog.com"
    search_path = "/sims4/"


# Wo Creator ihre Dateien ablegen – in dieser Reihenfolge bevorzugt (echte Datei-Hoster vor Patreon-Seiten)
FILE_HOSTS = ("simfileshare.net", "mediafire.com", "drive.google.com", "dropbox.com", "mega.nz",
              "sims4studio.com", "curseforge.com", "thesimsresource.com", "modthesims.info",
              "patreon.com/posts", "patreon.com")


def _host_rank(url):
    low = url.lower()
    return next((i for i, h in enumerate(FILE_HOSTS) if h in low), len(FILE_HOSTS))


class Tumblr(Source):
    """Tumblr: Die Suchseite enthält alle Treffer als JSON (<script id="___INITIAL_STATE___">) – mit Blog,
    Post-Link, Bildern und den Links im Text (meist SimFileShare, Patreon, Google Drive …)."""
    id = "tumblr"
    name = "Tumblr"
    homepage = "https://www.tumblr.com"
    login_url = "https://www.tumblr.com/login"
    description = "Viele Creator veröffentlichen hier. Treffer mit Bild und den Download-Links aus dem Beitrag."
    base = "https://www.tumblr.com"

    def search_url(self, query):
        q = query.strip()
        if "sims" not in q.lower():
            q = "sims 4 " + q
        return f"{self.base}/search/{quote(q)}"

    def search(self, query, session=None):
        return self.parse(fetch(session, self.search_url(query)))

    @staticmethod
    def _posts(node, out, depth=0):
        if depth > 14 or len(out) >= MAX_RESULTS:
            return
        if isinstance(node, dict):
            if node.get("postUrl") and node.get("blogName") and "content" in node:
                out.append(node)
                return
            for value in node.values():
                Tumblr._posts(value, out, depth + 1)
        elif isinstance(node, list):
            for value in node:
                Tumblr._posts(value, out, depth + 1)

    @staticmethod
    def _blocks(post):
        blocks = list(post.get("content") or [])
        for entry in post.get("trail") or []:          # Reblogs: der Inhalt steckt im Verlauf
            blocks += entry.get("content") or []
        return blocks

    def parse(self, page):
        raw = first(r'<script[^>]*id=Q___INITIAL_STATE___Q[^>]*>(.*?)</script>', page)
        try:
            state = json.loads(htmlmod.unescape(raw.strip())) if raw else {}
        except ValueError:
            try:
                state = json.loads(raw.strip())
            except ValueError:
                return []
        posts = []
        self._posts(state, posts)
        results, seen = [], set()
        for post in posts:
            if post["postUrl"] in seen:
                continue
            seen.add(post["postUrl"])
            blocks = self._blocks(post)
            image, texts, links = "", [], []
            for block in blocks:
                if block.get("type") == "image" and not image:
                    media = [m for m in block.get("media") or [] if m.get("url")]
                    fitting = [m for m in media if 300 <= (m.get("width") or 0) <= 700]
                    image = (fitting or media or [{}])[0].get("url", "")
                elif block.get("type") == "text":
                    texts.append(block.get("text") or "")
                    for fmt in block.get("formatting") or []:
                        if fmt.get("type") == "link" and fmt.get("url"):
                            links.append(fmt["url"])
                elif block.get("type") == "link" and block.get("url"):
                    links.append(block["url"])
            files = sorted(dict.fromkeys(u for u in links if _host_rank(u) < len(FILE_HOSTS)), key=_host_rank)
            title = (post.get("summary") or (texts[0] if texts else "") or post.get("slug", "")).strip()
            results.append(SearchResult(
                title=title.splitlines()[0][:120] if title else post["blogName"], url=post["postUrl"],
                source_id=self.id, image_url=image, creator=post["blogName"],
                description=" ".join(t for t in texts[1:4] if t)[:300],
                extra={"links": files, "download_seite": files[0] if files else post["postUrl"],
                       "nsfw": bool(post.get("isNsfw"))}))
        return results

    def download_urls(self, result, session=None):
        """Direkt ladbare Datei-Links aus dem Beitrag (SimFileShare & Co.). Liefert ein Link eine Seite statt der
        Datei, öffnet SimVault die Seite im eingebauten Browser."""
        return [u for u in result.extra.get("links", [])
                if any(h in u.lower() for h in ("simfileshare.net/download", "dl.dropboxusercontent.com"))]


class NewSea(Source):
    """NewSea (nur http): keine Suchfunktion, nur Listen. SimVault liest den Sims-4-Katalog (Frisuren,
    Accessoires, Make-up – rund 500 Einträge) einmal ein, merkt ihn sich eine Woche und sucht darin selbst.
    Stand November 2026: Freie Frisuren lädt ein Klick auf den Datei-Link (downfile.php) im Browser direkt
    herunter, ohne Konto. Ein Abruf per Skript liefert dagegen nur eine leere Seite – deshalb geht der
    Download über den eingebauten Browser. Donate-Frisuren gibt es nur angemeldet, sonst verlangt die Seite
    eine Registrierung. Anmelden geht über das Formular auf der Startseite (ID, Passwort, Bild-Code);
    SimVault speichert die Anmeldung wie bei allen Seiten verschlüsselt."""
    id = "newsea"
    name = "NewSea"
    homepage = "http://www.newseasims.com"
    login_url = "http://www.newseasims.com/"         # Anmeldeformular sitzt auf der Startseite
    description = ("Frisuren von NewSea. Durchsucht den Sims-4-Katalog der Seite (wird eine Woche zwischengespeichert). "
                   "Freie Frisuren ohne Konto; für Donate-Frisuren unter „Quellen“ anmelden.")
    base = "http://www.newseasims.com"
    sections = ((1, 15), (2, 16), (3, 12))          # Sims-4-Frisuren, -Accessoires, -Make-up
    max_pages = 60
    cache_days = 7
    ignore_words = {"newsea", "sims", "sims4", "ts4", "4", "hair", "hairstyle", "cc"}

    def search_url(self, query):
        return f"https://www.google.com/search?q=site%3Anewseasims.com+sims+4+{quote_plus(query.strip())}"

    def _cache_path(self):
        import os
        if os.name == "nt":
            base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "SimVault")
        else:
            base = os.path.join(os.path.expanduser("~"), ".config", "simvault")
        return os.path.join(base, "cache", "newsea.json")

    def parse_list(self, page):
        items = []
        for chunk in re.split(r"(?=<li\b)", page)[1:]:
            href = first(r'href=Q(inside-page\.php\?[^"\']*?id=\d+)Q', chunk)
            name = text(first(r'<td colspan=Q2Q[^>]*>(.*?)</td>', chunk)) or text(first(r'<img[^>]*alt=Q(V)Q', chunk))
            if not href or not name:
                continue
            image = first(r'<img[^>]*src=Q(imagefile/V)Q', chunk)
            items.append({"name": name, "url": urljoin(self.base + "/", htmlmod.unescape(href)),
                          "image": urljoin(self.base + "/", image) if image else "",
                          "creator": text(first(r"<td>\s*By ([^<]+)</td>", chunk)) or "newsea"})
        return items

    def catalog(self, session, refresh=False):
        """Alle Sims-4-Einträge (aus dem Zwischenspeicher, falls jünger als eine Woche)."""
        import os
        import time
        path = self._cache_path()
        if not refresh:
            try:
                if time.time() - os.path.getmtime(path) < self.cache_days * 86400:
                    with open(path, encoding="utf-8") as f:
                        return json.load(f)
            except (OSError, ValueError):
                pass
        items, seen = [], set()
        for cid, sid in self.sections:
            for page_no in range(1, self.max_pages + 1):
                page = fetch(session, f"{self.base}/list-page.php?page={page_no}&cid={cid}&sid={sid}&model=")
                new = [i for i in self.parse_list(page) if i["url"] not in seen]
                if not new:
                    break
                for item in new:
                    seen.add(item["url"])
                items += new
        if items:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(items, f, ensure_ascii=False)
            except OSError:
                pass
        return items

    def search(self, query, session=None):
        words = [w.lower() for w in re.split(r"[^A-Za-z0-9]+", query) if w and w.lower() not in self.ignore_words]
        if not words:
            return []
        items = self.catalog(session)

        def name_of(item):
            return re.sub(r"[^a-z0-9]+", "", item["name"].lower())

        hits = [i for i in items if all(w in name_of(i) for w in words)] or \
            [i for i in items if any(len(w) >= 4 and w in name_of(i) for w in words)]
        return [SearchResult(title=i["name"], url=i["url"], source_id=self.id, image_url=i["image"],
                             creator=i["creator"]) for i in hits[:MAX_RESULTS]]

    def download_urls(self, result, session=None):
        return []


class SexySims(Source):
    """SexySims (18+, Anmeldung nötig): gleiches Download-System wie früher bei ModTheSims – Suche nach einem
    Schlagwort (browse.php?tag=…&gs=4 für Sims 4), Treffer als <div class="downloadblock">, die Detailseite
    (download.php?t=…) enthält direkte Datei-Links (getfile.php). Ohne Anmeldung zeigt die Seite nichts."""
    id = "sexysims"
    name = "SexySims"
    homepage = "https://sexysims.info"
    login_url = "https://sexysims.info/login.php"
    needs_login = True
    adult = True
    description = "18+-Seite, Anmeldung nötig. Dateien lädt SimVault direkt mit deiner Anmeldung."
    base = "https://sexysims.info"

    def search_url(self, query):
        return f"{self.base}/browse.php?tag={quote_plus(query.strip())}&gs=4"

    def search(self, query, session=None):
        words = _split_words(query)
        urls = [self.search_url(query)] + ([self.search_url(w) for w in words if len(w) >= 4][:3] if len(words) > 1 else [])
        seen, results = set(), []
        for url in urls:
            page = fetch(session, url)
            if "You are not allowed to access" in page:
                raise OSError("SexySims zeigt Suchergebnisse nur angemeldet – unter „Quellen“ anmelden")
            for r in self.parse(page):
                if r.url not in seen:
                    seen.add(r.url)
                    results.append(r)
            if len(results) >= 10:
                break
        return results[:MAX_RESULTS]

    def parse(self, page):
        results = []
        for chunk in re.split(r'(?=<div class=["\']downloadblock)', page)[1:MAX_RESULTS + 1]:
            href = first(r'<p class=Qfont-large[^>]*>\s*<a href=Q(V)Q', chunk) or first(r'href=Q(/download\.php\?t=\d+)Q', chunk)
            if not href:
                continue
            image = first(r'<img(?=[^>]*featuredimage)[^>]*src=Q(V)Q', chunk)
            preview = text(first(r'id=Qpostbitpopover_\d+Q[^>]*>\s*<p[^>]*>(.*?)(?:<a [^>]*>more|</p>)', chunk))
            preview = re.sub(r"^click here to enlarge image\s*", "", preview, flags=re.I)
            # Lange Titel sind in der Liste mit „…“ gekürzt – der volle Titel steht im title-Attribut
            title = text(first(r'<p class=Qfont-large[^>]*>\s*<a [^>]*title=Q(V)Q', chunk)) or \
                text(first(r'<p class=Qfont-large[^>]*>\s*<a [^>]*>(.*?)</a>', chunk))
            results.append(SearchResult(
                title=title,
                url=urljoin(self.base, href), source_id=self.id, image_url=urljoin(self.base, image) if image else "",
                creator=text(first(r'by\s*<strong>\s*<a [^>]*>(.*?)</a>', chunk)),
                description=preview[:300]))
        return results

    def download_urls(self, result, session=None):
        page = fetch(session, result.url)
        urls = []
        for link in re.findall(r'href=["\']([^"\']*getfile\.php\?file=\d+[^"\']*)', page):
            link = htmlmod.unescape(link)
            if link not in urls:
                urls.append(link)
        return urls


class LoversLab(Source):
    """LoversLab (18+, Anmeldung nötig): Invision-Forum. Mit quick=1 liefert die Suche die Treffer direkt im HTML
    (sonst lädt die Seite sie per Skript nach); nodes=161 begrenzt auf „The Sims 4“ samt Unterkategorien.
    Die Seite sperrt schnelle Suchen hintereinander – deshalb genau eine Abfrage pro Suche.
    Herunterladen nur über die Dateiseite (Schutzschlüssel) -> eingebauter Browser."""
    id = "loverslab"
    name = "LoversLab"
    homepage = "https://www.loverslab.com"
    login_url = "https://www.loverslab.com/login/"
    needs_login = True
    adult = True
    description = "18+-Seite, Anmeldung nötig. Sucht in den Sims-4-Dateien; heruntergeladen wird im eingebauten Browser."
    base = "https://www.loverslab.com"
    sims4_category = 161

    def search_url(self, query):
        return (f"{self.base}/search/?q={quote_plus(query.strip())}&type=downloads_file&quick=1"
                f"&nodes={self.sims4_category}")

    def search(self, query, session=None):
        return self.parse(fetch(session, self.search_url(query)))

    def parse(self, page):
        results = []
        for chunk in re.split(r'(?=<li[^>]*class=["\'][^"\']*ipsStreamItem_contentBlock)', page)[1:MAX_RESULTS + 1]:
            href = first(r'<span class=QipsContainedVQ>\s*<a\s[^>]*?href=Q(V)Q', chunk)
            if not href or "/files/file/" not in href:
                continue
            image = first(r'<img src=Q(https?://V)Q[^>]*alt=QMore information', chunk) or \
                htmlmod.unescape(first(r'background-image:\s*url\(\s*(?:&quot;|["\'])?(https?:[^"\')&]+)', chunk))
            category = text(first(r'posted a file in\s*<a [^>]*>(.*?)</a>', chunk))
            results.append(SearchResult(
                title=text(first(r'<span class=QipsContainedVQ>\s*<a\s[^>]*>(.*?)</a>', chunk)),
                url=htmlmod.unescape(href).split("?")[0], source_id=self.id, image_url=image,
                creator=text(first(r'ipsStreamItem_status[^>]*>\s*<a [^>]*>(.*?)</a>', chunk)),
                description=text(first(r'data-findTerm[^>]*>(.*?)</div>', chunk))[:300],
                extra={"kategorie": category}))
        return results

    def download_urls(self, result, session=None):
        return []
