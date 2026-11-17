# Tests – Parser der CC-Seiten (gegen gespeicherte Beispielseiten)

from helpers import *  # noqa: F401,F403


TSR_PAGE = """<div class="browse-page"><div class="item-wrapper" data-item="{&quot;ID&quot;:&quot;1617735&quot;,
&quot;title&quot;:&quot;Wimpern 3D&quot;,&quot;description&quot;:&quot;Zwanzig Varianten&quot;,&quot;creator&quot;:&quot;Testerin&quot;,
&quot;free&quot;:&quot;1&quot;}"><a class="item-link" onclick="return x(this)"
href="/downloads/details/category/sims4-makeup/title/wimpern-3d/id/1617735/" rel="maingroup">
<div class="item-image" style="background: url('/scaled/3445/w-293h-220-3445644.jpg')"></div></a>
<a href="/downloads/details/category/sims4-makeup/title/wimpern-3d/id/1617735/">See More and Download</a></div>
<div class="item-wrapper" data-item="kaputt"><a class="item-link" href="/downloads/details/category/x/title/zweites-teil/id/2/">
<div class="item-image" style="background:url(/scaled/1/b.jpg)"></div></a></div>"""


CF_PAGE = """<div class=" project-card"><div class="art"><img id="row-image" alt="logo" src="https://media.forgecdn.net/a/1.jpg">
</div><a class="overlay-link" href="/sims4/create-a-sim/wimpern-s1"></a><a class="name" title="Go"
href="/sims4/create-a-sim/wimpern-s1"><span class="ellipsis">Wimpern S1 &amp; mehr</span></a><span class="author">
<span class="author-name"><a class="author-name is-link" href="/members/ivy"><span class="ellipsis">Ivy</span></a></span>
</span><a class=" download-cta btn-cta" rel="nofollow" href="/sims4/create-a-sim/wimpern-s1/download/6953394">Download</a>
<p class="description">Natürliche Wimpern</p></div><div class=" project-card"><p>ohne Link</p></div>"""


MTS_PAGE = """<li data-component="" class="smol-card-component"><div class="thumbnailwrapper">
<a href='/d/610965/mascara.html'><img class='featuredimage' loading='lazy' src='//thumbs2.modthesims2.com/img/1.attach' />
</a></div><div class="downloadDetails"><p class="downloadtitle clamped">
<a href='/d/610965/mascara.html' title="">Mascara -5 styles-</a></p><p class="downloadcreator" > by
<span class="downloadcreatorname"><strong><a href="/m/2404969">Vampi</a></strong></span></p>
<p class="downloadPreview"> Hey guys! <a href='/download.php?t=610965'>more...</a></p></li>"""


MTS_DETAIL = """<a class="downloadlink" href="https://chii.modthesims.info/getfile.php?file=1&amp;v=2">Mascara.rar</a>
<a style="float:right" class="downloadlink btn btn-small" href="https://chii.modthesims.info/getfile.php?file=1&amp;v=2">Download</a>
<a class="downloadlink" href="https://chii.modthesims.info/getfile.php?file=3&amp;v=4">Extra.package</a>"""


class SiteParserTests(unittest.TestCase):
    def test_tsr(self):
        from simvault.web.sources.sites import TheSimsResource
        src = TheSimsResource()
        results = src.parse(TSR_PAGE)
        self.assertEqual([(r.title, r.creator) for r in results], [("Wimpern 3D", "Testerin"), ("Zweites Teil", "")])
        self.assertEqual(results[0].image_url, "https://www.thesimsresource.com/scaled/3445/w-293h-220-3445644.jpg")
        self.assertEqual(results[0].url, "https://www.thesimsresource.com/downloads/details/category/sims4-makeup/"
                                         "title/wimpern-3d/id/1617735/")
        self.assertEqual(results[1].image_url, "https://www.thesimsresource.com/scaled/1/b.jpg")
        self.assertEqual(src.download_urls(results[0]), [])           # Download über die Seite (Browser)
        self.assertEqual(src.search_url("kijiko eyelash"),
                         "https://www.thesimsresource.com/downloads/browse/category/sims4/search/kijiko%20eyelash/")

    def test_curseforge(self):
        from simvault.web.sources.sites import CurseForge
        results = CurseForge().parse(CF_PAGE)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual((r.title, r.creator, r.description), ("Wimpern S1 & mehr", "Ivy", "Natürliche Wimpern"))
        self.assertEqual(r.image_url, "https://media.forgecdn.net/a/1.jpg")
        self.assertEqual(r.extra["download_seite"],
                         "https://www.curseforge.com/sims4/create-a-sim/wimpern-s1/download/6953394")

    def test_modthesims_with_files(self):
        from simvault.web.sources.sites import ModTheSims

        class Session:
            renderer = None

            def __init__(self, pages):
                self.pages, self.asked = pages, []

            def get(self, url):
                self.asked.append(url)
                return self.pages.get(url, "<html>nichts</html>")

        src = ModTheSims()
        results = src.parse(MTS_PAGE)
        r = results[0]
        self.assertEqual((r.title, r.creator, r.description), ("Mascara -5 styles-", "Vampi", "Hey guys!"))
        self.assertEqual(r.image_url, "https://thumbs2.modthesims2.com/img/1.attach")
        session = Session({r.url: MTS_DETAIL})
        self.assertEqual(src.download_urls(r, session), ["https://chii.modthesims.info/getfile.php?file=1&v=2",
                                                         "https://chii.modthesims.info/getfile.php?file=3&v=4"])
        # Suche mit Ersteller + Begriff: erst ganzer Begriff, dann Ersteller-Suche, dann einzelne Wörter
        session = Session({"https://modthesims.info/downloads.php?gs=4&creator=Vampi&tag=mascara": MTS_PAGE})
        found = src.search("Vampi mascara", session)
        self.assertEqual([x.title for x in found], ["Mascara -5 styles-"])
        self.assertEqual(session.asked[:2], ["https://modthesims.info/downloads.php?gs=4&tag=Vampi+mascara",
                                             "https://modthesims.info/downloads.php?gs=4&creator=Vampi&tag=mascara"])

    def test_blocked_page_uses_browser(self):
        from simvault.web.sources.sites import fetch

        class Session:
            def __init__(self, renderer):
                self.renderer = renderer

            def get(self, url):
                return "<title>Just a moment...</title><div id='cf-challenge'></div>"

            def render(self, url):
                return self.renderer(url)

        self.assertEqual(fetch(Session(lambda u: "<p>echt</p>"), "https://x"), "<p>echt</p>")
        from simvault.web.sources.base import CheckRequired
        with self.assertRaises(CheckRequired):                          # ohne Fenster: klar melden statt 0 Treffer
            fetch(Session(None), "https://x")

    def test_download_result_falls_back_to_browser_page(self):
        from simvault.app import core
        from simvault.web.sources.base import SearchResult
        cfg = {"sources_enabled": {}}
        r = SearchResult(title="x", url="https://www.curseforge.com/sims4/create-a-sim/x", source_id="curseforge",
                         extra={"download_seite": "https://www.curseforge.com/sims4/create-a-sim/x/download/1"})
        self.assertEqual(core.download_result(cfg, r, session=object()),
                         (None, "https://www.curseforge.com/sims4/create-a-sim/x/download/1"))


SIMSFINDS_PAGE = """<div class="_x1 _ptfcreations-item" data-item-id="407566" itemprop="itemListElement" itemscope>
<meta itemprop="position" content="1"><div class="_q9z _ellipsis" itemprop="name">3D Eyelashes: Pretty Princess by Learxfl</div>
<figure data-id="407566"><a class="_k3 _ptfdownload-link" href="https://www.simsfinds.com/downloads/407566/3d-eyelashes-sims4"
title="3D Eyelashes for The Sims 4" itemprop="url"><img src="https://img.simsfinds.com.br/d/1-gnd.jpg" alt="x" itemprop="image"></a>
</figure><div><a class="_z" data-type="hashtag" href="/en/downloads/sims4/eyelashes-802">#eyelashes</a>
<a data-type="type" href="/x">#alpha</a></div></div>
<div class="_x2" data-item-id="1" itemprop="itemListElement"><div itemprop="name">Ohne Link</div></div>"""


WP_PAGE = """<article class="post-1 post entry" aria-label="x"><div class="entry-content"><h2 class="entry-title">
<a class="entry-title-link" rel="bookmark" href="https://sims4updates.net/accessories/lashes-by-coffeemoon-at-tsr/">Thick lashes
by coffeemoon at TSR</a></h2><a class="entry-image-link" href="#"><img src="data:image/png;base64,AAAA"
class="post-image entry-image lazyload" data-src="https://sims4updates.net/wp-content/uploads/61-1.jpg" /></a>
<p>Filed Under: Accessories</p><p>Dicke Wimpern für Männer</p></div></article>
<div class="post-single-col-grid row"><a href="https://thesimscatalog.com/sims4/downloads/star/" class="post-thumbnail">
<img width="265" src="https://thesimscatalog.com/sims4/wp-content/uploads/Star.jpg" class="media-object wp-post-image"></a>
<h2 class="post-title"><a href="https://thesimscatalog.com/sims4/downloads/star/">Star Eyelashes 3D</a></h2>
<ul class="meta"><li class="post-author">Posted By : <a href="/author/tsr/" rel="author">The Sims Resource</a></li></ul></div>"""


def tumblr_page(posts):
    state = {"routeSet": "main", "queries": {"queries": [{"state": {"data": {"pages": [{"items": posts}]}}}]}}
    return ('<html><script type="application/json" id="___INITIAL_STATE___">'
            + html_escape(json.dumps(state)) + "</script></html>")


def html_escape(value):
    import html
    return html.escape(value, quote=False)


class MoreSiteParserTests(unittest.TestCase):
    def test_simsfinds(self):
        from simvault.web.sources.sites import SimsFinds
        src = SimsFinds()
        results = src.parse(SIMSFINDS_PAGE)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual((r.title, r.creator), ("3D Eyelashes: Pretty Princess by Learxfl", "Learxfl"))
        self.assertEqual(r.url, "https://www.simsfinds.com/downloads/407566/3d-eyelashes-sims4")
        self.assertEqual(r.image_url, "https://img.simsfinds.com.br/d/1-gnd.jpg")
        self.assertEqual(r.description, "#eyelashes")
        self.assertEqual(src.search_url("Kijiko Eye-lash!"), "https://www.simsfinds.com/results/sims4-kijiko-eye-lash")
        self.assertEqual(src.download_urls(r), [])

    def test_wordpress_both_layouts(self):
        from simvault.web.sources.sites import Sims4Updates, TheSimsCatalog
        updates = Sims4Updates().parse(WP_PAGE)
        self.assertEqual([(r.title, r.creator) for r in updates],
                         [("Thick lashes by coffeemoon at TSR", "coffeemoon"), ("Star Eyelashes 3D", "The Sims Resource")])
        self.assertEqual(updates[0].image_url, "https://sims4updates.net/wp-content/uploads/61-1.jpg")
        self.assertEqual(updates[0].description, "Dicke Wimpern für Männer")
        self.assertEqual(updates[1].image_url, "https://thesimscatalog.com/sims4/wp-content/uploads/Star.jpg")
        self.assertEqual(TheSimsCatalog().search_url("3d lashes"), "https://thesimscatalog.com/sims4/?s=3d+lashes")

    def test_wordpress_falls_back_to_longest_word(self):
        from simvault.web.sources.sites import Sims4Updates

        class Session:
            renderer = None
            asked = []

            def get(self, url):
                self.asked.append(url)
                return WP_PAGE if url.endswith("?s=coffeemoon") else "<html>Nothing found</html>"

        found = Sims4Updates().search("TSR coffeemoon", Session())
        self.assertEqual(len(found), 2)
        self.assertEqual(Session.asked, ["https://sims4updates.net/?s=TSR+coffeemoon",
                                         "https://sims4updates.net/?s=coffeemoon"])

    def test_tumblr_state_json(self):
        from simvault.web.sources.sites import Tumblr
        posts = [
            {"objectType": "post", "blogName": "veneriancc", "postUrl": "https://veneriancc.tumblr.com/post/1/douyin",
             "summary": "Douyin Eyelashes", "isNsfw": False, "content": [
                 {"type": "image", "media": [{"url": "https://64.media.tumblr.com/big.jpg", "width": 1280},
                                             {"url": "https://64.media.tumblr.com/mid.jpg", "width": 540}]},
                 {"type": "text", "text": "Douyin Eyelashes"},
                 {"type": "text", "text": "6 Varianten <Download>", "formatting": [
                     {"type": "link", "url": "https://www.patreon.com/posts/douyin-135696685"},
                     {"type": "link", "url": "http://www.simfileshare.net/download/5660449/"},
                     {"type": "link", "url": "https://buymeacoffee.com/Venerian"}]}]},
            {"objectType": "post", "blogName": "rebloggerin", "postUrl": "https://rebloggerin.tumblr.com/post/2",
             "summary": "", "slug": "reblog", "content": [], "trail": [{"content": [
                 {"type": "text", "text": "Haare von jemand anderem"},
                 {"type": "link", "url": "https://www.mediafire.com/file/abc/Haare.zip"}]}]},
        ]
        src = Tumblr()
        results = src.parse(tumblr_page(posts))
        self.assertEqual([(r.title, r.creator) for r in results],
                         [("Douyin Eyelashes", "veneriancc"), ("Haare von jemand anderem", "rebloggerin")])
        first_post = results[0]
        self.assertEqual(first_post.image_url, "https://64.media.tumblr.com/mid.jpg")
        self.assertEqual(first_post.extra["links"], ["http://www.simfileshare.net/download/5660449/",
                                                     "https://www.patreon.com/posts/douyin-135696685"])
        self.assertEqual(first_post.extra["download_seite"], "http://www.simfileshare.net/download/5660449/")
        self.assertEqual(src.download_urls(first_post), ["http://www.simfileshare.net/download/5660449/"])
        self.assertEqual(results[1].extra["download_seite"], "https://www.mediafire.com/file/abc/Haare.zip")
        self.assertEqual(src.search_url("Kijiko eyelash"), "https://www.tumblr.com/search/sims%204%20Kijiko%20eyelash")
        self.assertEqual(src.parse("<html>kein JSON</html>"), [])


NEWSEA_LIST = """<ul><li><table class="p-title" width="370px"><tr class="border-bottom"><td colspan="2">StarfoldSweet+</td>
<td align="right"><img src="images/down_ico3.gif" alt="down" /><span>7</span></td></tr></table>
<div><a href="inside-page.php?cid=1&id=1111"><img src="imagefile/suoli/1786385059.jpg" alt="StarfoldSweet+" /></a></div>
<table><tr><td>By newsea</td><td align="right"><a href="inside-page.php?cid=1&id=1111">Show Details</a></td></tr></table></li>
<li><table class="p-title"><tr><td colspan="2">CitrusMousse</td></tr></table>
<div><a href="inside-page.php?cid=1&amp;id=1110"><img src="imagefile/suoli/2.jpg" alt="CitrusMousse" /></a></div></li></ul>"""


class NewSeaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = {k: os.environ.get(k) for k in ("APPDATA", "HOME")}
        os.environ["APPDATA"] = os.environ["HOME"] = self.tmp

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp)

    def test_catalog_search_and_cache(self):
        from simvault.web.sources.sites import NewSea

        class Session:
            renderer = None
            calls = 0

            def get(self, url):
                Session.calls += 1
                return NEWSEA_LIST if "page=1&cid=1&sid=15" in url else "<html></html>"

        src = NewSea()
        self.assertEqual(src.parse_list(NEWSEA_LIST)[1]["url"], "http://www.newseasims.com/inside-page.php?cid=1&id=1110")
        found = src.search("Newsea StarfoldSweet", Session())
        self.assertEqual([(r.title, r.creator) for r in found], [("StarfoldSweet+", "newsea")])
        self.assertEqual(found[0].image_url, "http://www.newseasims.com/imagefile/suoli/1786385059.jpg")
        self.assertEqual(found[0].url, "http://www.newseasims.com/inside-page.php?cid=1&id=1111")
        calls = Session.calls
        self.assertEqual([r.title for r in src.search("citrus mousse", Session())], ["CitrusMousse"])
        self.assertEqual(Session.calls, calls)                       # zweite Suche aus dem Zwischenspeicher
        self.assertEqual(src.search("newsea hair", Session()), [])   # nur Füllwörter
        self.assertEqual(src.download_urls(found[0]), [])
        self.assertEqual(src.login_url, "http://www.newseasims.com/")      # Anmeldung möglich, nicht Pflicht
        self.assertFalse(src.needs_login)


SEXYSIMS_PAGE = """<div class="row cf" id="masonrycontainer"><div class="span12"><div class="downloadblock">
<div class="downloadinfoblock cf"><div class="thumbimage well"><a href='/download.php?t=176786'>
<img class='featuredimage' src='https://thumbs2.sexysims.info//img/2/330656.largethumb.jpg' /></a></div>
<div><p class="font-large bold" > <a href="/download.php?t=176786" title="High School Sex Classes (High School Years)">High
School Sex Classes (High...</a> </p><p class="muted"> by <strong><a href="/member.php?u=1">BiscuitButt</a></strong> 1st Jan</p>
</div></div><div id="postbitpopover_176786" style="display:none"><p style="line-height:1.3em;">click here to enlarge image
Ersetzt die Highschool-Kurse <a href='/download.php?t=176786'>more...</a></p></div></div>"""


SEXYSIMS_DETAIL = """<td width="70%"><a href="https://chii.sexysims.info/getfile.php?file=330655"> {BiscuitButt} V5.rar</a>
<a href="https://chii.sexysims.info/getfile.php?file=330655">Download</a></td>"""


LOVERSLAB_PAGE = """<ol><li class="ipsStreamItem ipsStreamItem_contentBlock ipsStreamItem_expanded" data-role="activityItem">
<div class="ipsStreamItem_header"><h2 class="ipsStreamItem_title"><span><a href="https://www.loverslab.com/files/file/1-x/?do=getNewComment"
title="Go to first unread post"><i class="fa fa-circle"></i></a></span> <span class="ipsContained ipsType_break"><a
href="https://www.loverslab.com/files/file/52834-pretty-flowers-lingerie/?tab=details" data-linktype="link">Pretty Flowers
<mark class="ipsMatch1">Lingerie</mark></a> </span></h2><p class="ipsType_reset ipsStreamItem_status ipsType_blendLinks">
<a href="https://www.loverslab.com/profile/1-grayvixen/" class="ipsType_break">GrayVixen</a> posted a file in
<a href="https://www.loverslab.com/files/category/200-clothing/">Clothing</a></p></div>
<div class="ipsStreamItem_snippet"><span style='background-image: url( &quot;https://static.loverslab.com/s/1.thumb.jpg&quot; )'
class='ipsThumb'><img src='https://static.loverslab.com/s/1.thumb.jpg' alt='More information about &quot;x&quot;' loading="lazy">
</span><div class='ipsType_richText' data-searchable data-findTerm> Maxis Match, 17 Varianten </div></div></li></ol>"""


class AdultSiteParserTests(unittest.TestCase):
    def test_sexysims(self):
        from simvault.web.sources.sites import SexySims

        class Session:
            renderer = None

            def get(self, url):
                return SEXYSIMS_DETAIL

        src = SexySims()
        r = src.parse(SEXYSIMS_PAGE)[0]
        self.assertEqual((r.title, r.creator, r.description),
                         ("High School Sex Classes (High School Years)", "BiscuitButt", "Ersetzt die Highschool-Kurse"))
        self.assertEqual(r.url, "https://sexysims.info/download.php?t=176786")
        self.assertEqual(r.image_url, "https://thumbs2.sexysims.info//img/2/330656.largethumb.jpg")
        self.assertEqual(src.download_urls(r, Session()), ["https://chii.sexysims.info/getfile.php?file=330655"])
        self.assertTrue(src.needs_login and src.adult)

        class NotLoggedIn:
            renderer = None

            def get(self, url):
                return "<html>Error! You are not allowed to access this forum.</html>"

        with self.assertRaises(OSError):
            src.search("hair", NotLoggedIn())

    def test_loverslab(self):
        from simvault.web.sources.sites import LoversLab
        src = LoversLab()
        r = src.parse(LOVERSLAB_PAGE)[0]
        self.assertEqual((r.title, r.creator, r.description, r.extra["kategorie"]),
                         ("Pretty Flowers Lingerie", "GrayVixen", "Maxis Match, 17 Varianten", "Clothing"))
        self.assertEqual(r.url, "https://www.loverslab.com/files/file/52834-pretty-flowers-lingerie/")
        self.assertEqual(r.image_url, "https://static.loverslab.com/s/1.thumb.jpg")
        self.assertEqual(src.search_url("lingerie set"), "https://www.loverslab.com/search/?q=lingerie+set"
                                                         "&type=downloads_file&quick=1&nodes=161")
        self.assertEqual(src.download_urls(r), [])


if __name__ == "__main__":
    unittest.main()
