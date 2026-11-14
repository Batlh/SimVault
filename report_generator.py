# Modul: report_generator.py
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
# Datenbank-Speicherung:
# - SQLite (Standard für Einzelnutzer, leichtgewichtig, serverlos)
# - Geplant: MySQL/PostgreSQL als separates Plugin für Fortgeschrittene
#   -> einfach einen weiteren Database Adapter neben _write_sqlite schreiben
# Optional: Custom Branding (Titel, Logo) – Titel kommt bereits aus config.json

import os
import csv
import json
import sqlite3
from html import escape
from collections import Counter
from datetime import datetime

import cc_searcher

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
                    db_path="simvault_data.db", formats=("html", "csv", "json", "md"),
                    app_name="SimVault", missing=None, missing_info=None, found=None, conflicts=None,
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
                       "meldung": f"{c['teile']} gemeinsame{'s Teil' if c['teile'] == 1 else ' Teile'} "
                                  f"({c['identisch']} identisch, "
                                  f"{c['unterschiedlich']} unterschiedlich). {c['empfehlung']}",
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
    if db_path:
        _write_sqlite(db_path, now, summary, issues, data_rows, missing)
    return written


def _mb(n):
    return f"{n / (1024 * 1024):.1f} MB"


def _write_csv(path, data_rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel erkennt Umlaute
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Datei", "Kategorie", "Status", "Spielstände", "Tray-Einträge", "Größe (Bytes)", "Ressourcen"])
        for d in data_rows:
            writer.writerow([d["datei"], d["kategorie"], d["status"], ", ".join(d["spielstaende"]),
                             d["tray_eintraege"], d["groesse_bytes"], d["ressourcen"]])
    return path


def _write_missing_csv(path, missing):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["ID", "Art", "Anzahl", "Verwendet von", "Quellen"])
        for m in missing:
            writer.writerow([m["id"], m["art"], m["anzahl"], " | ".join(m["verwendet_von"]), ", ".join(m["quellen"])])
    return path


def _parts_summary(parts):
    """["Haare (Steckplatz 2)", "Haare (Steckplatz 2)", "Schuhe (Steckplatz 8)"] -> "2× Haare, 1× Schuhe" """
    counts = Counter(p["art"].split(" (")[0] for p in parts)
    return ", ".join(f"{n}× {art}" for art, n in counts.most_common())


def _write_md(path, app_name, summary, issues, data_rows, missing=None, households=(), found=None):
    lines = [f"# {app_name} – Bericht vom {summary['erstellt'].replace('T', ' ')}", "",
             f"- Mods-Ordner: `{summary['mods_ordner']}`",
             f"- Spielstände: {', '.join(summary['spielstaende']) or '—'}",
             f"- Dateien: {summary['anzahl_dateien']}", ""]
    lines += ["## Status", ""] + [f"- **{k}**: {v}" for k, v in summary["status"].items()] + [""]
    if issues:
        lines += ["## Probleme", ""]
        for i in issues:
            lines.append(f"- **{i['schwere']} – {i['art']}**: {i['meldung']}")
            lines += [f"  - `{f}`" for f in i["dateien"][:50]]
        lines.append("")
    if missing is not None:
        lines += ["## Fehlende CC", "", f"_{summary.get('fehlend_info') or ''}_", ""]
        if missing:
            lines += ["| ID | Art | Anzahl | Verwendet von | Quellen |", "|---|---|---|---|---|"]
            for m in missing:
                who = ", ".join(m["verwendet_von"][:5]).replace("|", "\\|")
                lines.append(f"| `{m['id']}` | {m['art']} | {m['anzahl']} | {who} | {', '.join(m['quellen'])} |")
        else:
            lines.append("Keine fehlende CC gefunden.")
        lines.append("")
    if found:
        lines += ["## Auf deinem PC gefunden", "",
                  f"{found['gefunden']} von {found['gesucht']} fehlenden Teilen gefunden.", ""]
        for item in found["dateien"]:
            where = f"{item['pfad']} → {item['archiv_eintrag']}" if item["archiv_eintrag"] else item["pfad"]
            lines.append(f"- **{item['anzahl_ids']} Teile** ({', '.join(item['arten'])}): `{where}`")
        for u in sorted(found["nicht_lesbar"], key=lambda x: not x.get("sims")):
            mark = " **(Sims-Bezug)**" if u.get("sims") else ""
            lines.append(f"- nicht durchsuchbar{mark}: `{u['pfad']}` ({u['grund']})")
        lines.append("")
    if households:
        lines += ["## Bibliothek: Einträge mit fehlender CC", ""]
        for h in households:
            by = f" von **{h['ersteller']}**" if h["ersteller"] else ""
            lines.append(f"### {h['name']}{by} ({h['typ']}, {h['datum'] or 'Datum unbekannt'})")
            lines.append(f"- Fehlt: {_parts_summary(h['fehlend'])}")
            if h["beschreibung"]:
                lines.append(f"- Beschreibung: {h['beschreibung'][:300]}")
            for link in h["links"]:
                lines.append(f"- CC-Link aus der Beschreibung: {link}")
            lines.append(f"- [Im Web suchen]({h['suche']})")
            lines.append("")
    lines += ["## Mods", "", "| Datei | Kategorie | Status | Spielstände | Tray |", "|---|---|---|---|---|"]
    for d in data_rows:
        name = d["datei"].replace("|", "\\|")
        lines.append(f"| {name} | {d['kategorie']} | {d['status']} | {', '.join(d['spielstaende'])} | {d['tray_eintraege'] or ''} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _write_sqlite(db_path, now, summary, issues, data_rows, missing=None):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created TEXT, mods_folder TEXT, saves TEXT, summary TEXT);
            CREATE TABLE IF NOT EXISTS mod_files (
                scan_id INTEGER REFERENCES scans(id), path TEXT, category TEXT, status TEXT,
                saves TEXT, tray_items INTEGER, size INTEGER, resources INTEGER);
            CREATE TABLE IF NOT EXISTS issues (
                scan_id INTEGER REFERENCES scans(id), severity TEXT, kind TEXT, message TEXT, files TEXT);
            CREATE TABLE IF NOT EXISTS missing_cc (
                scan_id INTEGER REFERENCES scans(id), id TEXT, kind TEXT, uses INTEGER, used_by TEXT, sources TEXT);
        """)
        cur.execute("INSERT INTO scans (created, mods_folder, saves, summary) VALUES (?, ?, ?, ?)",
                    (now.isoformat(timespec="seconds"), summary["mods_ordner"],
                     json.dumps(summary["spielstaende"]), json.dumps(summary, ensure_ascii=False)))
        scan_id = cur.lastrowid
        cur.executemany("INSERT INTO mod_files VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [(scan_id, d["datei"], d["kategorie"], d["status"], ", ".join(d["spielstaende"]),
                          d["tray_eintraege"], d["groesse_bytes"], d["ressourcen"]) for d in data_rows])
        cur.executemany("INSERT INTO issues VALUES (?, ?, ?, ?, ?)",
                        [(scan_id, i["schwere"], i["art"], i["meldung"], json.dumps(i["dateien"], ensure_ascii=False))
                         for i in issues])
        cur.executemany("INSERT INTO missing_cc VALUES (?, ?, ?, ?, ?, ?)",
                        [(scan_id, m["id"], m["art"], m["anzahl"], json.dumps(m["verwendet_von"], ensure_ascii=False),
                          ", ".join(m["quellen"])) for m in (missing or [])])
        conn.commit()
    finally:
        conn.close()


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
    out = [f"<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'><title>{e(app_name)} Bericht</title>",
           f"<style>{_CSS}</style></head><body><div class='wrap'>",
           f"<h1>{logo}{e(app_name)} – Bericht</h1>",
           f"<div class='meta'>{e(summary['erstellt'].replace('T', ' '))} · Mods-Ordner: {e(summary['mods_ordner'])}<br>"
           f"Spielstände: {e(', '.join(summary['spielstaende']) or '—')}</div>",
           "<div class='cards'>",
           f"<div class='card'><b>{summary['anzahl_dateien']}</b>Mod-Dateien</div>"]
    for status in STATUS_ORDER:
        if status in summary["status"]:
            out.append(f"<div class='card' title='{e(STATUS_HELP.get(status, ''))}'><b>{summary['status'][status]}</b>{e(status)}</div>")
    if missing is not None:
        out.append(f"<div class='card'><b>{len(missing)}</b>fehlende CC</div>")
    if summary["groesse_ungenutzt_bytes"]:
        out.append(f"<div class='card'><b>{_mb(summary['groesse_ungenutzt_bytes'])}</b>ungenutzte CC</div>")
    out.append("</div>")

    if issues:
        out.append("<h2>Probleme</h2>")
        for i in issues:
            files = "".join(f"<li>{e(f)}</li>" for f in i["dateien"])
            out.append(f"<div class='issue {e(i['schwere'])}'><b>{e(i['schwere'])} – {e(i['art'])}:</b> "
                       f"{e(i['meldung'])}<ul>{files}</ul></div>")

    if missing is not None:
        out.append("<h2>Fehlende CC</h2><div class='meta'>CAS-Teile und Objekte, die in Spielständen oder der "
                   "Bibliothek verwendet werden, aber in keinem installierten Paket stecken. Im Spiel erscheinen "
                   "sie unsichtbar oder fehlen. Die ID hilft beim Wiederfinden (z. B. mit Sims 4 Studio).<br>"
                   f"{e(summary.get('fehlend_info') or '')}</div>")
        if missing:
            extra = "<th>Gefunden in</th>" if found else ""
            out.append("<table><tr><th>ID</th><th>Art</th><th>Anzahl</th><th>Verwendet von</th><th>Quellen</th>"
                       f"{extra}</tr>")
            for m in missing:
                who = m["verwendet_von"]
                shown = "<br>".join(e(w) for w in who[:8]) + (f"<br>… {len(who) - 8} weitere" if len(who) > 8 else "")
                cell = ""
                if found:
                    files = (found_at or {}).get(m["id"], [])
                    cell = f"<td class='s-genutzt'>{e(', '.join(files))}</td>" if files else "<td>—</td>"
                out.append(f"<tr><td><code>{e(m['id'])}</code></td><td>{e(m['art'])}</td><td>{m['anzahl']}</td>"
                           f"<td>{shown}</td><td>{e(', '.join(m['quellen']))}</td>{cell}</tr>")
            out.append("</table>")
        else:
            out.append("<p>Keine fehlende CC gefunden. 🎉</p>")

    if found:
        out.append(f"<h2>Auf deinem PC gefunden</h2><div class='meta'>{found['gefunden']} von {found['gesucht']} "
                   "fehlenden Teilen gefunden. Durchsucht: " + e(", ".join(found["ordner"])) + "</div>")
        if found["dateien"]:
            out.append("<table><tr><th>Datei</th><th>Teile</th><th>Art</th><th>Für</th><th>Fundort</th></tr>")
            for item in found["dateien"]:
                where = e(item["pfad"]) + (f" → {e(item['archiv_eintrag'])}" if item["archiv_eintrag"] else "")
                more = item.get("weitere_fundorte") or []
                if more:
                    where += f"<br><span class='meta'>auch in: {'<br>'.join(e(m) for m in more)}</span>"
                out.append(f"<tr><td>{e(item['datei'])}</td><td>{item['anzahl_ids']}</td>"
                           f"<td>{e(', '.join(item['arten']))}</td>"
                           f"<td>{e(', '.join(item.get('verwendet_von', [])[:5]))}</td><td>{where}</td></tr>")
            out.append("</table><p>Zurückholen ohne neue Suche: <code>py -3 main.py restore</code> "
                       "(kopiert nach Mods/SimVault_wiederhergestellt, überschreibt nichts; "
                       "einzelne auslassen mit <code>--ohne TEXT</code>)</p>")
        if found["nicht_lesbar"]:
            sims = [u for u in found["nicht_lesbar"] if u.get("sims")]
            rest = [u for u in found["nicht_lesbar"] if not u.get("sims")]
            if sims:
                out.append("<div class='issue Fehler'><b>Nicht durchsuchbar – mit Sims-Bezug</b><ul>"
                           + "".join(f"<li>{e(u['pfad'])} – {e(u['grund'])}</li>" for u in sims) + "</ul></div>")
            if rest:
                out.append(f"<details><summary>{len(rest)} weitere nicht durchsuchbare Archive ohne erkennbaren "
                           "Sims-Bezug</summary><ul class='meta'>"
                           + "".join(f"<li>{e(u['pfad'])} – {e(u['grund'])}</li>" for u in rest)
                           + "</ul></details>")

    if households:
        out.append("<h2>Bibliothek: Einträge mit fehlender CC</h2><div class='meta'>Gespeicherte Haushalte, "
                   "deren CC fehlt. Der Ersteller ist die Galerie-ID – über ihn findest du meist die CC-Liste "
                   "(Galerie, Tumblr, Patreon, YouTube).</div>")
        for h in households:
            by = f" von <b>{e(h['ersteller'])}</b>" if h["ersteller"] else ""
            orig = (f" (ursprünglich von {e(h['original_ersteller'])})"
                    if h["original_ersteller"] and h["original_ersteller"] != h["ersteller"] else "")
            out.append(f"<div class='issue'><b>{e(h['name'])}</b>{by}{orig} · {e(h['typ'])} · {e(h['datum'])}"
                       f"<br>Fehlt: {e(_parts_summary(h['fehlend']))}")
            if h["beschreibung"]:
                out.append(f"<br><span class='meta'>{_linkify(h['beschreibung'][:600])}</span>")
            out.append(f"<br><a href='{e(h['suche'])}' target='_blank' rel='noopener'>Im Web suchen</a></div>")

    if broken_names:
        out.append("<h2>Defekte Dateien neu suchen</h2><table><tr><th>Datei</th><th>Suchen auf</th></tr>")
        for name in broken_names:
            links = " · ".join(f"<a href='{e(url)}' target='_blank' rel='noopener'>{e(site)}</a>"
                               for site, url in cc_searcher.search_links(name).items())
            out.append(f"<tr><td>{e(name)}</td><td>{links}</td></tr>")
        out.append("</table>")

    out.append("<h2>Mods</h2><div class='meta'>"
               + "<br>".join(f"<b>{e(k)}</b>: {e(v)}" for k, v in STATUS_HELP.items())
               + "</div><input id='q' placeholder='Filtern …' oninput='filt()'>")
    out.append("<table id='mods'><thead><tr><th>Datei</th><th>Kategorie</th><th>Status</th>"
               "<th>Spielstände</th><th>Tray</th><th>Größe</th></tr></thead><tbody>")
    for r in rows:
        m = r["mod"]
        css = "s-" + r["status"].split(" ")[0]
        out.append(f"<tr><td>{e(m.rel_path)}</td><td>{e(m.category)}</td><td class='{css}'>{e(r['status'])}</td>"
                   f"<td>{e(', '.join(r['saves']))}</td><td>{r['tray'] or ''}</td><td>{_mb(m.size)}</td></tr>")
    out.append(f"</tbody></table></div><script>{_JS}</script></body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(out))
    return path
