# Modul: simvault/storage/report_generator.py
# Funktion: Erstellt Berichte (HTML, CSV, JSON, Markdown) über den Mods-Ordner und die
#           CC-Nutzung in Spielständen und speichert alles zusätzlich in einer SQLite-Datenbank.
#
# Inhalt:
# - Übersicht (Anzahl Mods nach Kategorie und Status)
# - Probleme im Mods-Ordner (zu tief, beschädigt, Duplikate, Konflikte, ...)
# - Pro Mod-Datei: Kategorie, Status (genutzt / ungenutzt / ...), in welchen Spielständen, Tray
# - Suchlinks für defekte Dateien
# - Fehlende CC: CAS-Teile/Objekte, die verwendet werden, aber nicht installiert sind
#
# Datenbank-Speicherung (database.py):
# - SQLite (Standard für Einzelnutzer, leichtgewichtig, serverlos)
# - MySQL/MariaDB oder PostgreSQL für Fortgeschrittene (Treiber selbst installieren)
# Optional: Custom Branding (Titel, Logo) – Titel kommt bereits aus config.json

import os
import csv
import json
from html import escape
from collections import Counter
from datetime import datetime

from simvault.finder import cc_searcher
from simvault.app import i18n
from simvault.app.i18n import t, tr

# Sprache: wie die Oberfläche (ui_language); die JSON-Datei bleibt deutsch (Schlüssel und Werte), weil
# SimVault sie selbst wieder einliest (z. B. „restore“).

STATUS_ORDER = ["defekt", "ungenutzt", "genutzt", "nicht nachweisbar", "nicht prüfbar", "—"]
STATUS_HELP = {
    "genutzt": "kommt in einem Spielstand oder in der Bibliothek vor",
    "ungenutzt": "CAS-/Objekt-CC, die nirgends verwendet wird – Aufräumkandidat",
    "nicht nachweisbar": "Tuning/Gameplay – wird oft nicht im Spielstand gespeichert, also nicht automatisch ungenutzt",
    "nicht prüfbar": "Script-Mod – lässt sich nicht über den Spielstand prüfen",
    "defekt": "Datei beschädigt oder leer",
}


def _rows(mod_scan, usage):
    if usage is not None:
        rows = usage
    else:
        rows = [{"mod": m, "status": "defekt" if m.category == "Defekt" else "—", "saves": [], "tray": 0}
                for m in mod_scan.mods]
    return sorted(rows, key=lambda r: (STATUS_ORDER.index(r["status"]) if r["status"] in STATUS_ORDER else 99,
                                       r["mod"].rel_path.lower()))


def _row_dict(r):
    m = r["mod"]
    return {
        "datei": m.rel_path,
        "kategorie": m.category,
        "status": r["status"],
        "spielstaende": r["saves"],
        "tray_eintraege": r["tray"],
        "groesse_bytes": m.size,
        "ressourcen": m.resource_count,
    }


def generate_report(mod_scan, usage=None, saves=None, output_dir="reports",
                    db_path=None, formats=("html", "csv", "json", "md"),
                    app_name="SimVault", missing=None, missing_info=None, found=None, conflicts=None,
                    db=None,
                    logo_path=None):
    """Schreibt die Berichte und gibt die Liste der erzeugten Dateien zurück."""
    os.makedirs(output_dir, exist_ok=True)
    households = []
    if isinstance(missing, dict):
        households = missing.get("bibliothek", [])
        missing = missing.get("teile", [])
    found_at = {}  # ID -> Dateien, in denen sie gefunden wurde
    for item in (found or {}).get("dateien", []):
        for i in item["ids"]:
            found_at.setdefault(i, []).append(item["datei"])
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    rows = _rows(mod_scan, usage)
    data_rows = [_row_dict(r) for r in rows]
    saves = [os.path.basename(s) for s in (saves or [])]
    status_count = Counter(r["status"] for r in rows)
    category_count = Counter(r["mod"].category for r in rows)
    broken_names = [r["mod"].rel_path for r in rows if r["status"] == "defekt"]

    summary = {
        "erstellt": now.isoformat(timespec="seconds"),
        "mods_ordner": mod_scan.folder,
        "spielstaende": saves,
        "anzahl_dateien": len(rows),
        "kategorien": dict(category_count),
        "status": dict(status_count),
        "groesse_ungenutzt_bytes": sum(r["mod"].size for r in rows if r["status"] == "ungenutzt"),
        "fehlend": None if missing is None else len(missing),
        "fehlend_info": missing_info,
    }
    issues = [{"schwere": i.severity, "art": i.kind, "meldung": i.message, "dateien": i.files}
              for i in mod_scan.issues if not (conflicts and i.kind == "Konflikt")]
    # Geprüfte Konflikte ersetzen die pauschale Meldung des Scanners: mit Art, Nutzung und Empfehlung
    for c in (conflicts or {}).get("konflikte", []):
        serious = c["art"] in ("Konflikt", "Überschreibung") and c["genutzt"]
        issues.append({"schwere": "Fehler" if serious else "Hinweis", "art": c["art"],
                       "meldung": t("{} gemeinsames Teil ({} identisch, {} unterschiedlich). {}" if c["teile"] == 1
                                    else "{} gemeinsame Teile ({} identisch, {} unterschiedlich). {}",
                                    c["teile"], c["identisch"], c["unterschiedlich"], c["empfehlung"]),
                       "dateien": c["dateien"]})

    written = []
    base = os.path.join(output_dir, f"report_{stamp}")
    if "html" in formats:
        written.append(_write_html(base + ".html", app_name, summary, issues, rows, broken_names, missing,
                                   households, found, found_at, logo=_logo_tag(logo_path)))
    if "csv" in formats:
        written.append(_write_csv(base + ".csv", data_rows))
        if missing:
            written.append(_write_missing_csv(base + "_fehlend.csv", missing))
    if "json" in formats:
        path = base + ".json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"zusammenfassung": summary, "probleme": issues, "fehlend": missing or [],
                       "fehlend_bibliothek": households, "fundstellen": found or {},
                       "konflikte": (conflicts or {}).get("konflikte", []),
                       "entfernbar": (conflicts or {}).get("entfernbar", []),
                       "aufloesbar": (conflicts or {}).get("aufloesbar", []), "mods": data_rows},
                      f, indent=2, ensure_ascii=False)
        written.append(path)
    if "md" in formats:
        written.append(_write_md(base + ".md", app_name, summary, issues, data_rows, missing, households, found))
    if db is None and db_path:
        db = {"type": "sqlite", "sqlite_path": db_path}
    if db:
        from simvault.storage import database
        try:
            database.write_scan(db, now, summary, issues, data_rows, missing)
        except Exception as e:          # Datenbank nicht erreichbar: Berichte trotzdem schreiben
            import logging
            logging.getLogger(__name__).warning("Datenbank nicht beschrieben: %s", e)
    return written


def _mb(n):
    return f"{n / (1024 * 1024):.1f} MB"


def _write_csv(path, data_rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel erkennt Umlaute
        writer = csv.writer(f, delimiter=";")
        writer.writerow([t("Datei"), t("Kategorie"), t("Status"), t("Spielstände"), t("Tray-Einträge"),
                         t("Größe (Bytes)"), t("Ressourcen")])
        for d in data_rows:
            writer.writerow([d["datei"], tr(d["kategorie"]), tr(d["status"]), ", ".join(d["spielstaende"]),
                             d["tray_eintraege"], d["groesse_bytes"], d["ressourcen"]])
    return path


def _write_missing_csv(path, missing):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["ID", t("Art"), t("Anzahl"), t("Verwendet von"), t("Quellen")])
        for m in missing:
            writer.writerow([m["id"], tr(m["art"]), m["anzahl"], " | ".join(m["verwendet_von"]), ", ".join(m["quellen"])])
    return path


def _parts_summary(parts):
    """["Haare (Steckplatz 2)", "Haare (Steckplatz 2)", "Schuhe (Steckplatz 8)"] -> "2× Haare, 1× Schuhe" """
    counts = Counter(p["art"].split(" (")[0] for p in parts)
    return ", ".join(f"{n}× {tr(art)}" for art, n in counts.most_common())


def _write_md(path, app_name, summary, issues, data_rows, missing=None, households=(), found=None):
    lines = [t("# {} – Bericht vom {}", app_name, summary["erstellt"].replace("T", " ")), "",
             t("- Mods-Ordner: `{}`", summary["mods_ordner"]),
             t("- Spielstände: {}", ", ".join(summary["spielstaende"]) or "—"),
             t("- Dateien: {}", summary["anzahl_dateien"]), ""]
    lines += ["## " + t("Status"), ""] + [f"- **{tr(k)}**: {v}" for k, v in summary["status"].items()] + [""]
    if issues:
        lines += ["## " + t("Probleme"), ""]
        for i in issues:
            lines.append(f"- **{tr(i['schwere'])} – {tr(i['art'])}**: {tr(i['meldung'])}")
            lines += [f"  - `{f}`" for f in i["dateien"][:50]]
        lines.append("")
    if missing is not None:
        lines += ["## " + t("Fehlende CC"), "", f"_{summary.get('fehlend_info') or ''}_", ""]
        if missing:
            lines += ["| ID | " + " | ".join(t(x) for x in ("Art", "Anzahl", "Verwendet von", "Quellen")) + " |",
                      "|---|---|---|---|---|"]
            for m in missing:
                who = ", ".join(m["verwendet_von"][:5]).replace("|", "\\|")
                lines.append(f"| `{m['id']}` | {tr(m['art'])} | {m['anzahl']} | {who} | {', '.join(m['quellen'])} |")
        else:
            lines.append(t("Keine fehlende CC gefunden."))
        lines.append("")
    if found:
        lines += ["## " + t("Auf deinem PC gefunden"), "",
                  t("{} von {} fehlenden Teilen gefunden.", found["gefunden"], found["gesucht"]), ""]
        for item in found["dateien"]:
            where = f"{item['pfad']} → {item['archiv_eintrag']}" if item["archiv_eintrag"] else item["pfad"]
            lines.append(t("- **{} Teile** ({}): `{}`", item["anzahl_ids"], ", ".join(tr(a) for a in item["arten"]), where))
        for u in sorted(found["nicht_lesbar"], key=lambda x: not x.get("sims")):
            mark = t(" **(Sims-Bezug)**") if u.get("sims") else ""
            lines.append(t("- nicht durchsuchbar{}: `{}` ({})", mark, u["pfad"], u["grund"]))
        lines.append("")
    if households:
        lines += ["## " + t("Bibliothek: Einträge mit fehlender CC"), ""]
        for h in households:
            by = t(" von **{}**", h["ersteller"]) if h["ersteller"] else ""
            lines.append(f"### {h['name']}{by} ({tr(h['typ'])}, {h['datum'] or t('Datum unbekannt')})")
            lines.append(t("- Fehlt: {}", _parts_summary(h["fehlend"])))
            if h["beschreibung"]:
                lines.append(t("- Beschreibung: {}", h["beschreibung"][:300]))
            for link in h["links"]:
                lines.append(t("- CC-Link aus der Beschreibung: {}", link))
            lines.append(f"- [{t('Im Web suchen')}]({h['suche']})")
            lines.append("")
    lines += ["## Mods", "", "| " + " | ".join(t(x) for x in ("Datei", "Kategorie", "Status", "Spielstände", "Tray"))
              + " |", "|---|---|---|---|---|"]
    for d in data_rows:
        name = d["datei"].replace("|", "\\|")
        lines.append(f"| {name} | {tr(d['kategorie'])} | {tr(d['status'])} | {', '.join(d['spielstaende'])} | "
                     f"{d['tray_eintraege'] or ''} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


_CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f5f7;color:#222}
.wrap{max-width:1200px;margin:0 auto;padding:24px}
h1{margin:0 0 4px}h2{margin-top:32px}
.meta{color:#666;font-size:14px}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}
.card{background:#fff;border-radius:8px;padding:12px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px}
.card b{display:block;font-size:24px}
table{border-collapse:collapse;width:100%;background:#fff;font-size:14px}
th,td{padding:6px 10px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}
th{background:#fafafa;position:sticky;top:0;cursor:pointer}
.s-genutzt{color:#1b7f3b}.s-ungenutzt{color:#b26a00}.s-defekt{color:#c62828;font-weight:600}
.s-nicht{color:#777}
.issue{background:#fff;border-left:4px solid #b26a00;padding:8px 12px;margin:8px 0;border-radius:4px}
.issue.Fehler{border-color:#c62828}
.issue ul{margin:6px 0 0;padding-left:20px;font-size:13px;max-height:200px;overflow:auto}
input{padding:6px 10px;width:300px;margin:8px 0}
a{color:#1565c0}
"""

_JS = """
function filt(){const q=document.getElementById('q').value.toLowerCase();
document.querySelectorAll('#mods tbody tr').forEach(r=>{r.style.display=r.textContent.toLowerCase().includes(q)?'':'none'})}
document.querySelectorAll('#mods th').forEach((th,i)=>th.onclick=()=>{const tb=th.closest('table').tBodies[0];
const rows=[...tb.rows];const asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
rows.sort((a,b)=>a.cells[i].textContent.localeCompare(b.cells[i].textContent,'de',{numeric:true})*(asc?1:-1));
rows.forEach(r=>tb.appendChild(r))});
"""


def _linkify(text):
    """Text escapen und enthaltene Links klickbar machen."""
    import re
    out, last = [], 0
    for m in re.finditer(r"https?://[^\s<>\"']+", text):
        out.append(escape(text[last:m.start()]))
        url = escape(m.group(0))
        out.append(f"<a href='{url}' target='_blank' rel='noopener'>{url}</a>")
        last = m.end()
    out.append(escape(text[last:]))
    return "".join(out)


def _tray_picture(path):
    """Vorschaubild eines Bibliothekseintrags als eingebettetes JPEG (oder leer)."""
    if not path:
        return ""
    import base64
    from simvault.analysis import thumbnails
    data = thumbnails.tray_image(path)
    if not data:
        return ""
    jpeg, _alpha = thumbnails.split_alpha(data)
    kind = "png" if jpeg.startswith(b"\x89PNG") else "jpeg"
    return (f"<img src='data:image/{kind};base64,{base64.b64encode(jpeg).decode('ascii')}' alt='' "
            "style='float:left;height:110px;margin:0 14px 4px 0;border-radius:6px;background:#fff'>")


def _logo_tag(logo_path):
    """Eigenes Logo (Custom Branding) als eingebettetes Bild – der Bericht bleibt eine einzelne Datei."""
    if not logo_path or not os.path.isfile(logo_path):
        return ""
    kinds = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif", ".svg": "svg+xml", ".webp": "webp"}
    kind = kinds.get(os.path.splitext(logo_path)[1].lower())
    try:
        if not kind or os.path.getsize(logo_path) > 2 * 1024 * 1024:
            return ""
        import base64
        with open(logo_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""
    return f"<img src='data:image/{kind};base64,{data}' alt='' style='height:44px;vertical-align:middle;margin-right:12px'>"


def _write_html(path, app_name, summary, issues, rows, broken_names, missing=None, households=(),
                found=None, found_at=None, logo=""):
    e = escape
    lang = i18n.language()
    out = [f"<!DOCTYPE html><html lang='{lang}'><head><meta charset='utf-8'><title>{e(t('{} Bericht', app_name))}</title>",
           f"<style>{_CSS}</style></head><body><div class='wrap'>",
           f"<h1>{logo}{e(t('{} – Bericht', app_name))}</h1>",
           f"<div class='meta'>{e(summary['erstellt'].replace('T', ' '))} · {e(t('Mods-Ordner: {}', summary['mods_ordner']))}<br>"
           f"{e(t('Spielstände: {}', ', '.join(summary['spielstaende']) or '—'))}</div>",
           "<div class='cards'>",
           f"<div class='card'><b>{summary['anzahl_dateien']}</b>{e(t('Mod-Dateien'))}</div>"]
    for status in STATUS_ORDER:
        if status in summary["status"]:
            out.append(f"<div class='card' title='{e(t(STATUS_HELP.get(status, '')))}'><b>{summary['status'][status]}</b>"
                       f"{e(tr(status))}</div>")
    if missing is not None:
        out.append(f"<div class='card'><b>{len(missing)}</b>{e(t('fehlende CC'))}</div>")
    if summary["groesse_ungenutzt_bytes"]:
        out.append(f"<div class='card'><b>{_mb(summary['groesse_ungenutzt_bytes'])}</b>{e(t('ungenutzte CC'))}</div>")
    out.append("</div>")

    if issues:
        out.append(f"<h2>{e(t('Probleme'))}</h2>")
        for i in issues:
            files = "".join(f"<li>{e(f)}</li>" for f in i["dateien"])
            out.append(f"<div class='issue {e(i['schwere'])}'><b>{e(tr(i['schwere']))} – {e(tr(i['art']))}:</b> "
                       f"{e(tr(i['meldung']))}<ul>{files}</ul></div>")

    if missing is not None:
        out.append(f"<h2>{e(t('Fehlende CC'))}</h2><div class='meta'>"
                   + e(t("CAS-Teile und Objekte, die in Spielständen oder der Bibliothek verwendet werden, aber in keinem "
                         "installierten Paket stecken. Im Spiel erscheinen sie unsichtbar oder fehlen. Die ID hilft beim "
                         "Wiederfinden (z. B. mit Sims 4 Studio)."))
                   + f"<br>{e(summary.get('fehlend_info') or '')}</div>")
        if missing:
            extra = f"<th>{e(t('Gefunden in'))}</th>" if found else ""
            out.append("<table><tr><th>ID</th>" + "".join(f"<th>{e(t(x))}</th>" for x in
                                                          ("Art", "Anzahl", "Verwendet von", "Quellen")) + f"{extra}</tr>")
            for m in missing:
                who = m["verwendet_von"]
                shown = "<br>".join(e(w) for w in who[:8]) + ("<br>" + e(t("… {} weitere", len(who) - 8))
                                                              if len(who) > 8 else "")
                cell = ""
                if found:
                    files = (found_at or {}).get(m["id"], [])
                    cell = f"<td class='s-genutzt'>{e(', '.join(files))}</td>" if files else "<td>—</td>"
                out.append(f"<tr><td><code>{e(m['id'])}</code></td><td>{e(tr(m['art']))}</td><td>{m['anzahl']}</td>"
                           f"<td>{shown}</td><td>{e(', '.join(m['quellen']))}</td>{cell}</tr>")
            out.append("</table>")
        else:
            out.append(f"<p>{e(t('Keine fehlende CC gefunden. 🎉'))}</p>")

    if found:
        out.append(f"<h2>{e(t('Auf deinem PC gefunden'))}</h2><div class='meta'>"
                   + e(t("{} von {} fehlenden Teilen gefunden. Durchsucht: {}", found["gefunden"], found["gesucht"],
                         ", ".join(found["ordner"]))) + "</div>")
        if found["dateien"]:
            out.append("<table><tr>" + "".join(f"<th>{e(t(x))}</th>" for x in ("Datei", "Teile", "Art", "Für", "Fundort"))
                       + "</tr>")
            for item in found["dateien"]:
                where = e(item["pfad"]) + (f" → {e(item['archiv_eintrag'])}" if item["archiv_eintrag"] else "")
                more = item.get("weitere_fundorte") or []
                if more:
                    where += f"<br><span class='meta'>{e(t('auch in:'))} {'<br>'.join(e(m) for m in more)}</span>"
                out.append(f"<tr><td>{e(item['datei'])}</td><td>{item['anzahl_ids']}</td>"
                           f"<td>{e(', '.join(tr(a) for a in item['arten']))}</td>"
                           f"<td>{e(', '.join(item.get('verwendet_von', [])[:5]))}</td><td>{where}</td></tr>")
            out.append("</table><p>" + t("Zurückholen ohne neue Suche: <code>py -3 main.py restore</code> "
                                         "(kopiert nach Mods/SimVault_wiederhergestellt, überschreibt nichts; "
                                         "einzelne auslassen mit <code>--ohne TEXT</code>)") + "</p>")
        if found["nicht_lesbar"]:
            sims = [u for u in found["nicht_lesbar"] if u.get("sims")]
            rest = [u for u in found["nicht_lesbar"] if not u.get("sims")]
            if sims:
                out.append(f"<div class='issue Fehler'><b>{e(t('Nicht durchsuchbar – mit Sims-Bezug'))}</b><ul>"
                           + "".join(f"<li>{e(u['pfad'])} – {e(u['grund'])}</li>" for u in sims) + "</ul></div>")
            if rest:
                out.append(f"<details><summary>{e(t('{} weitere nicht durchsuchbare Archive ohne erkennbaren Sims-Bezug', len(rest)))}"
                           "</summary><ul class='meta'>"
                           + "".join(f"<li>{e(u['pfad'])} – {e(u['grund'])}</li>" for u in rest)
                           + "</ul></details>")

    if households:
        out.append(f"<h2>{e(t('Bibliothek: Einträge mit fehlender CC'))}</h2><div class='meta'>"
                   + e(t("Gespeicherte Haushalte, Grundstücke und Räume, deren CC fehlt. Der Ersteller ist die Galerie-ID – "
                         "über ihn findest du meist die CC-Liste (Galerie, Tumblr, Patreon, YouTube).")) + "</div>")
        for n, h in enumerate(households):
            by = t(" von <b>{}</b>", e(h["ersteller"])) if h["ersteller"] else ""
            orig = (t(" (ursprünglich von {})", e(h["original_ersteller"]))
                    if h["original_ersteller"] and h["original_ersteller"] != h["ersteller"] else "")
            picture = _tray_picture(h.get("bild")) if n < 80 else ""     # Bericht bleibt eine einzelne Datei
            out.append(f"<div class='issue' style='overflow:auto'>{picture}<b>{e(h['name'])}</b>{by}{orig} · "
                       f"{e(tr(h['typ']))} · {e(h['datum'])}"
                       f"<br>{e(t('Fehlt: {}', _parts_summary(h['fehlend'])))}")
            if h["beschreibung"]:
                out.append(f"<br><span class='meta'>{_linkify(h['beschreibung'][:600])}</span>")
            out.append(f"<br><a href='{e(h['suche'])}' target='_blank' rel='noopener'>{e(t('Im Web suchen'))}</a></div>")

    if broken_names:
        out.append(f"<h2>{e(t('Defekte Dateien neu suchen'))}</h2><table><tr><th>{e(t('Datei'))}</th>"
                   f"<th>{e(t('Suchen auf'))}</th></tr>")
        for name in broken_names:
            links = " · ".join(f"<a href='{e(url)}' target='_blank' rel='noopener'>{e(site)}</a>"
                               for site, url in cc_searcher.search_links(name).items())
            out.append(f"<tr><td>{e(name)}</td><td>{links}</td></tr>")
        out.append("</table>")

    out.append("<h2>Mods</h2><div class='meta'>"
               + "<br>".join(f"<b>{e(tr(k))}</b>: {e(t(v))}" for k, v in STATUS_HELP.items())
               + f"</div><input id='q' placeholder='{e(t('Filtern …'))}' oninput='filt()'>")
    out.append("<table id='mods'><thead><tr>" + "".join(f"<th>{e(t(x))}</th>" for x in
                                                       ("Datei", "Kategorie", "Status", "Spielstände", "Tray", "Größe"))
               + "</tr></thead><tbody>")
    for r in rows:
        m = r["mod"]
        css = "s-" + r["status"].split(" ")[0]
        out.append(f"<tr><td>{e(m.rel_path)}</td><td>{e(tr(m.category))}</td><td class='{css}'>{e(tr(r['status']))}</td>"
                   f"<td>{e(', '.join(r['saves']))}</td><td>{r['tray'] or ''}</td><td>{_mb(m.size)}</td></tr>")
    out.append(f"</tbody></table></div><script>{_JS.replace(chr(39) + 'de' + chr(39), repr(lang))}</script></body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(out))
    return path
