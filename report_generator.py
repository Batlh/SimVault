# Modul: report_generator.py
# Funktion: Erstellt Berichte (HTML, CSV, JSON, Markdown) über den Mods-Ordner und die
#           CC-Nutzung in Spielständen und speichert alles zusätzlich in einer SQLite-Datenbank.
#
# Inhalt:
# - Übersicht (Anzahl Mods nach Kategorie und Status)
# - Probleme im Mods-Ordner (zu tief, beschädigt, Duplikate, Konflikte, ...)
# - Pro Mod-Datei: Kategorie, Status (genutzt / ungenutzt / ...), in welchen Spielständen, Tray
# - Suchlinks für defekte Dateien

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
                    app_name="SimVault"):
    """Schreibt die Berichte und gibt die Liste der erzeugten Dateien zurück."""
    os.makedirs(output_dir, exist_ok=True)
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
    }
    issues = [{"schwere": i.severity, "art": i.kind, "meldung": i.message, "dateien": i.files}
              for i in mod_scan.issues]

    written = []
    base = os.path.join(output_dir, f"report_{stamp}")
    if "html" in formats:
        written.append(_write_html(base + ".html", app_name, summary, issues, rows, broken_names))
    if "csv" in formats:
        written.append(_write_csv(base + ".csv", data_rows))
    if "json" in formats:
        path = base + ".json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"zusammenfassung": summary, "probleme": issues, "mods": data_rows},
                      f, indent=2, ensure_ascii=False)
        written.append(path)
    if "md" in formats:
        written.append(_write_md(base + ".md", app_name, summary, issues, data_rows))
    if db_path:
        _write_sqlite(db_path, now, summary, issues, data_rows)
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


def _write_md(path, app_name, summary, issues, data_rows):
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
    lines += ["## Mods", "", "| Datei | Kategorie | Status | Spielstände | Tray |", "|---|---|---|---|---|"]
    for d in data_rows:
        name = d["datei"].replace("|", "\\|")
        lines.append(f"| {name} | {d['kategorie']} | {d['status']} | {', '.join(d['spielstaende'])} | {d['tray_eintraege'] or ''} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _write_sqlite(db_path, now, summary, issues, data_rows):
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


def _write_html(path, app_name, summary, issues, rows, broken_names):
    e = escape
    out = [f"<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'><title>{e(app_name)} Bericht</title>",
           f"<style>{_CSS}</style></head><body><div class='wrap'>",
           f"<h1>{e(app_name)} – Bericht</h1>",
           f"<div class='meta'>{e(summary['erstellt'].replace('T', ' '))} · Mods-Ordner: {e(summary['mods_ordner'])}<br>"
           f"Spielstände: {e(', '.join(summary['spielstaende']) or '—')}</div>",
           "<div class='cards'>",
           f"<div class='card'><b>{summary['anzahl_dateien']}</b>Mod-Dateien</div>"]
    for status in STATUS_ORDER:
        if status in summary["status"]:
            out.append(f"<div class='card' title='{e(STATUS_HELP.get(status, ''))}'><b>{summary['status'][status]}</b>{e(status)}</div>")
    if summary["groesse_ungenutzt_bytes"]:
        out.append(f"<div class='card'><b>{_mb(summary['groesse_ungenutzt_bytes'])}</b>ungenutzte CC</div>")
    out.append("</div>")

    if issues:
        out.append("<h2>Probleme</h2>")
        for i in issues:
            files = "".join(f"<li>{e(f)}</li>" for f in i["dateien"])
            out.append(f"<div class='issue {e(i['schwere'])}'><b>{e(i['schwere'])} – {e(i['art'])}:</b> "
                       f"{e(i['meldung'])}<ul>{files}</ul></div>")

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
