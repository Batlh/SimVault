# Modul: report_generator.py
# Funktion: Erstellt strukturierte Berichte (HTML, CSV, JSON, Markdown) über fehlende CCs und Suchergebnisse und speichert sie zusätzlich in einer Datenbank (SQLite mit Option auf MySQL)

# Aufgaben:
# - Aus fehlenden CC-IDs und Suchergebnissen einen übersichtlichen Bericht erstellen
# - Ausgabeformate:
#   - HTML (für schnelle Ansicht im Browser, mit Bootstrap-Template)
#   - CSV (für Tabellenansicht und Import in Excel/Sheets)
#   - JSON (für Weiterverarbeitung durch APIs und Tools)
#   - Markdown (.md) (für lesbare, formatierte Textberichte)
#   - Datenbank-Speicherung:
#     - SQLite (Standard für Einzelnutzer, leichtgewichtig, serverlos)
#     - Optional: MySQL/PostgreSQL Plugin (für Profis / größere Setups)

# Geplante Features:
# - Export als HTML
# - Export als CSV
# - Export als JSON
# - Export als Markdown
# - Speicherung aller Daten in einer SQLite-Datenbank (.db)
# - Automatische Timestamp- und Dateinamengenerierung
# - Optional: Custom Branding (Titel, Logo)

# Strukturvorschlag:
# - Funktion: generate_report(missing_cc, cc_alternatives) → Erstellt HTML, CSV, JSON, Markdown Berichte und speichert zusätzlich in einer SQLite-Datenbank

# Anmerkung:
# - MySQL- oder PostgreSQL-Support wird als **separates Plugin für Fortgeschrittene** implementiert.

import os
import json
import csv
import sqlite3
from datetime import datetime

def generate_report(missing_cc, cc_alternatives, output_dir='reports', db_path='simvault_data.db'):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. HTML Export
    html_path = os.path.join(output_dir, f'report_{timestamp}.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write("<html><head><title>SimVault Report</title>")
        f.write('<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body>')
        f.write("<div class='container'><h1>Missing CC Report</h1><table class='table table-striped'>")
        f.write("<thead><tr><th>ID</th><th>Alternative Sources</th></tr></thead><tbody>")
        for cc_id in missing_cc:
            alternatives = cc_alternatives.get(cc_id, [])
            alt_links = ' | '.join(f"<a href='{link}' target='_blank'>{link}</a>" for link in alternatives)
            f.write(f"<tr><td>{cc_id}</td><td>{alt_links}</td></tr>")
        f.write("</tbody></table></div></body></html>")

    # 2. CSV Export
    csv_path = os.path.join(output_dir, f'report_{timestamp}.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ID', 'Alternative Sources'])
        for cc_id in missing_cc:
            alternatives = cc_alternatives.get(cc_id, [])
            writer.writerow([cc_id, ', '.join(alternatives)])

    # 3. JSON Export
    json_path = os.path.join(output_dir, f'report_{timestamp}.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        data = {cc_id: cc_alternatives.get(cc_id, []) for cc_id in missing_cc}
        json.dump(data, f, indent=4, ensure_ascii=False)

    # 4. Markdown Export
    md_path = os.path.join(output_dir, f'report_{timestamp}.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# SimVault Missing CC Report\n\n")
        f.write("| ID | Alternative Sources |\n")
        f.write("|----|---------------------|\n")
        for cc_id in missing_cc:
            alternatives = cc_alternatives.get(cc_id, [])
            alt_links = ', '.join(alternatives)
            f.write(f"| {cc_id} | {alt_links} |\n")

    # 5. SQLite Export
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS missing_cc (
            id TEXT PRIMARY KEY,
            alternatives TEXT,
            timestamp TEXT
        )
    ''')
    for cc_id in missing_cc:
        alternatives = ', '.join(cc_alternatives.get(cc_id, []))
        cursor.execute('''
            INSERT OR REPLACE INTO missing_cc (id, alternatives, timestamp)
            VALUES (?, ?, ?)
        ''', (cc_id, alternatives, timestamp))
    conn.commit()
    conn.close()

    print(f"Reports generated successfully in '{output_dir}' and saved to database '{db_path}'.")

    # Hinweis:
    # Für Profi-User: MySQL-Support könnte später als Plugin eingebaut werden.
    # -> Einfach einen weiteren Database Adapter schreiben!
