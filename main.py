# main.py – Einstiegspunkt von SimVault (Kommandozeile)
#
# Beispiele:
#   python main.py                      Analyse: Mods-Ordner + neuester Spielstand + Bibliothek
#   python main.py analyze --all-saves  alle Spielstände einbeziehen
#   python main.py analyze --save "C:\...\Slot_00000002.save"
#   python main.py scan                 nur Mods-Ordner prüfen (ohne Spielstand)
#   python main.py find                 fehlende CC auf dem PC suchen (Downloads, alte Mods-Ordner …)
#   python main.py find "D:\Alte Mods" --restore   … in bestimmten Ordnern, Funde zurückholen
#   python main.py find --ganzer-pc     zusätzlich das komplette Laufwerk C: durchsuchen
#   python main.py restore --ohne WickedWhims   Funde aus dem letzten Suchbericht zurückholen
#   python main.py backup mods          Backup des Mods-Ordners (Modus aus config.json)
#   python main.py backup saves --mode delta
#   python main.py config               zeigt die verwendeten Pfade
#   python main.py setup                einrichten: Sims-Ordner, Spielordner, Entpacker für RAR/7z, Laufwerke

import os
import sys
import argparse
import logging

import config as cfg_mod
from i18n import t, tr


def _setup_logging(verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")


def _progress(msg):
    print(f"  … {msg}", flush=True)


def _check_folder(path, label):
    if not path or not os.path.isdir(path):
        print(t("{} nicht gefunden: {}", t(label), path or t("(nicht gesetzt)")))
        print(t("Bitte den Pfad in config.json eintragen (sims_folder oder den einzelnen Ordner)."))
        return False
    return True


def cmd_config(cfg, args):
    import archive_tools
    for key in ("sims_folder", "mods_folder", "savegames_folder", "tray_folder",
                "game_folder", "backup_folder", "report_folder"):
        path = cfg.get(key, "")
        state = "ok" if path and os.path.isdir(path) else t("fehlt")
        print(f"{key:18} {state:6} {path}")
    tools = archive_tools.tools_from_config(cfg)
    print(f"{'extractor':18} {'ok' if tools else t('aus'):6} "
          f"{(archive_tools.TOOL_NAMES[tools[0][0]] + ' – ' + tools[0][1]) if tools else t('RAR/7z werden übersprungen')}")
    print(f"{'search_drives':18} {t('ja') if cfg.get('search_drives', True) else t('nein')}")
    print("\n" + t("Konfigurationsdatei: {}", os.path.abspath(args.config)))
    return 0


def _scan_mods(cfg):
    from mod_folder_scanner import scan_mods_folder
    print(t("Scanne Mods-Ordner: {}", cfg["mods_folder"]))
    return scan_mods_folder(cfg["mods_folder"], progress=lambda i, n: _progress(t("{}/{} Dateien", i, n)))


def _print_summary(mod_scan, usage, missing=None):
    from collections import Counter
    print("\n" + t("{} Mod-Dateien gefunden.", len(mod_scan.mods)))
    for cat, n in Counter(m.category for m in mod_scan.mods).most_common():
        print(f"  {tr(cat):18} {n}")
    if usage is not None:
        print("\n" + t("Nutzung:"))
        for status, n in Counter(r["status"] for r in usage).most_common():
            print(f"  {tr(status):18} {n}")
    if missing is not None:
        parts = missing["teile"]
        if parts:
            print("\n" + t("Fehlende CC: {} verschiedene Teile/Objekte", len(parts)))
            for m in parts[:10]:
                print(f"  {m['id']}  {tr(m['art'])[:28]:28} {m['anzahl']:>4}×  {', '.join(m['verwendet_von'][:2])}")
            if len(parts) > 10:
                print("  " + t("… {} weitere im Bericht", len(parts) - 10))
            if missing["bibliothek"]:
                print("\n" + t("Bibliotheks-Einträge mit fehlender CC: {}", len(missing["bibliothek"])))
                for h in missing["bibliothek"][:10]:
                    by = t(" von {}", h["ersteller"]) if h["ersteller"] else ""
                    print("  " + t("{:>3} fehlend  {}{}", len(h["fehlend"]), h["name"], by))
        else:
            print("\n" + t("Fehlende CC: keine gefunden"))
    issues = [i for i in mod_scan.issues if i.kind != "Konflikt"]
    if issues:
        print("\n" + t("{} Problem(e):", len(issues)))
        for issue in issues:
            print("  " + t("[{}] {}: {} Datei(en)", tr(issue.severity), tr(issue.kind), len(issue.files)))


def _print_conflicts(result):
    """Geprüfte Konflikte: was sich überschneidet, wie, und was zu tun ist."""
    conflicts = result["konflikte"]
    if not conflicts:
        print("\n" + t("Konflikte: keine"))
        return
    from collections import Counter
    kinds = Counter(c["art"] for c in conflicts)
    print("\n" + t("Konflikte geprüft: {}", ", ".join(f"{n}× {tr(k)}" for k, n in kinds.items())))
    for c in conflicts[:12]:
        used = t(", {} in Benutzung", c["genutzt"]) if c["genutzt"] else ""
        print(f"  [{tr(c['art'])}] {' ↔ '.join(c['namen'])}")
        print("      " + t("{} gemeinsames Teil ({} identisch, {} unterschiedlich{})" if c["teile"] == 1 else
                           "{} gemeinsame Teile ({} identisch, {} unterschiedlich{})",
                           c["teile"], c["identisch"], c["unterschiedlich"], used))
        print(f"      → {c['empfehlung']}")
    if len(conflicts) > 12:
        print("  " + t("… {} weitere im Bericht", len(conflicts) - 12))
    todo = []
    if result["entfernbar"]:
        size = sum(e["groesse"] for e in result["entfernbar"]) / 1048576
        todo.append(t("{} überflüssige Datei(en) aussortieren ({:.1f} MB)", len(result["entfernbar"]), size))
    if result.get("aufloesbar"):
        todo.append(t("{} Konflikt(e) mit veralteter Fassung auflösen", len(result["aufloesbar"])))
    if todo:
        print("\n" + t("Sicher machbar: {} – mit: py -3 main.py conflicts --aufraeumen", t(" und ").join(todo)))


def _write_report(cfg, mod_scan, usage=None, saves=None, missing=None, missing_info=None, found=None,
                  conflicts=None):
    from report_generator import generate_report
    files = generate_report(mod_scan, usage, saves, missing=missing, missing_info=missing_info, found=found,
                            conflicts=conflicts,
                            output_dir=cfg["report_folder"],
                            db=cfg["database"],
                            formats=cfg["report_formats"],
                            app_name=cfg["branding"].get("app_name", "SimVault"),
                            logo_path=cfg["branding"].get("logo_path"))
    print("\n" + t("Berichte:"))
    for f in files:
        print(f"  {os.path.abspath(f)}")
    return files


def cmd_scan(cfg, args):
    if not _check_folder(cfg["mods_folder"], "Mods-Ordner"):
        return 1
    mod_scan = _scan_mods(cfg)
    _print_summary(mod_scan, None)
    _write_report(cfg, mod_scan)
    return 0


def cmd_analyze(cfg, args):
    from savegame_analyzer import find_saves, analyze_usage
    if not _check_folder(cfg["mods_folder"], "Mods-Ordner"):
        return 1

    if args.save:
        saves = args.save
    else:
        saves = find_saves(cfg["savegames_folder"])
        if not args.all_saves:
            saves = saves[:1]
    missing_files = [s for s in saves if not os.path.isfile(s)]
    if missing_files:
        print(t("Spielstand nicht gefunden: {}", ", ".join(missing_files)))
        return 1
    if not saves:
        print(t("Kein Spielstand gefunden in {} – es wird nur die Bibliothek geprüft.", cfg["savegames_folder"]))

    mod_scan = _scan_mods(cfg)
    print(t("Lese Spielstände und Bibliothek …"))
    tray = None if args.no_tray else cfg.get("tray_folder")
    id_usage = {}
    usage = analyze_usage(mod_scan, saves, tray_folder=tray, progress=_progress, id_usage=id_usage)

    missing = missing_info = None
    if not args.no_missing:
        missing, missing_info = _find_missing(cfg, mod_scan, saves, tray)
    import core
    conflicts = core.check_conflicts(cfg, mod_scan, id_usage, _progress)

    _print_summary(mod_scan, usage, missing)
    _print_conflicts(conflicts)
    _write_report(cfg, mod_scan, usage, saves, missing, missing_info, conflicts=conflicts)
    if missing and missing["teile"]:
        print("\n" + t('Tipp: Mit "python main.py find" suchst du die fehlende CC auf deinem PC '
                       "(Downloads, alte Mods-Ordner, ZIP-Archive)."))
    return 0


def _find_missing(cfg, mod_scan, saves, tray):
    from missing_cc import find_missing, index_game_content
    known = set(mod_scan.id_lookup())
    game = cfg.get("game_folder")
    if game and os.path.isdir(game):
        print(t("Lese Spielinhalte aus {} (beim ersten Mal etwas länger) …", game))
        known |= index_game_content(game, cache_path=cfg.get("game_cache", "game_ids_cache.json"),
                                    progress=_progress)
        info = t("Abgleich mit Mods-Ordner und Spielordner ({})", game)
    else:
        info = t("Abgleich mit dem Mods-Ordner; Spielordner nicht gefunden – "
                 "EA-Inhalte werden an ihren kleineren IDs erkannt")
    return find_missing(saves, tray, known, progress=_progress), info


def cmd_find(cfg, args):
    from savegame_analyzer import find_saves
    import cc_finder
    if not _check_folder(cfg["mods_folder"], "Mods-Ordner"):
        return 1
    import archive_tools
    folders = cc_finder.search_locations(cfg, args.folders,
                                         drives=cfg.get("search_drives", True) and not args.ohne_laufwerke,
                                         whole_pc=args.ganzer_pc)
    if not folders:
        print(t("Keine Suchordner gefunden. Ordner angeben: python main.py find \"D:\\Alte Mods\""))
        return 1

    mod_scan = _scan_mods(cfg)
    saves = find_saves(cfg["savegames_folder"])          # alle Spielstände
    print(t("Ermittle fehlende CC aus {} Spielständen und der Bibliothek …", len(saves)))
    missing, info = _find_missing(cfg, mod_scan, saves, cfg.get("tray_folder"))
    parts = missing["teile"]
    if not parts:
        print(t("Es fehlt keine CC – nichts zu suchen. 🎉"))
        return 0

    print(t("{} fehlende Teile. Durchsuche:", len(parts)))
    for f in folders:
        print(f"  {f}")
    tools = archive_tools.tools_from_config(cfg)
    if tools:
        kind, path = tools[0]
        print(t("Entpacker für RAR/7z: {} ({})", archive_tools.TOOL_NAMES[kind], path))
    else:
        print(t("Kein Entpacker für RAR/7z – diese Archive werden übersprungen. "
                "Tipp: winget install 7zip.7zip, dann py -3 main.py setup"))
    wanted = {int(p["id"], 16) for p in parts}
    import tempfile
    temp_base = cfg.get("temp_folder") or None
    if temp_base:
        os.makedirs(temp_base, exist_ok=True)
    cc_finder.cleanup_stale_temp(temp_base)   # Reste abgebrochener Läufe entfernen
    # Entpacktes wird pro Archiv sofort wieder gelöscht; nur bei --restore bleiben die Funde
    # selbst bis zum Zurückholen liegen. Der Ordner verschwindet am Ende in jedem Fall.
    with tempfile.TemporaryDirectory(prefix=cc_finder.TEMP_PREFIX, dir=temp_base) as work_dir:
        hits, unreadable = cc_finder.search(folders, wanted, exclude=[cfg["mods_folder"]], progress=_progress,
                                            work_dir=work_dir, tools=tools, keep_hits=args.restore,
                                            max_archive_mb=cfg.get("max_archive_mb", 4096))
        found, n_found = cc_finder.summarize(hits, parts)
        restored = failed = None
        skipped = []
        if found and args.restore and _backup_before_restore(cfg, args):
            restored, failed = cc_finder.restore(found, cfg["mods_folder"], exclude=args.ohne or [], tools=tools,
                                                 work_dir=work_dir, progress=_progress, skipped=skipped)
    for item in found:
        item.pop("temp_datei", None)  # Temp-Ordner ist jetzt gelöscht

    print("\n" + t("Gefunden: {} von {} fehlenden Teilen in {} Datei(en).", n_found, len(parts), len(found)))
    for item in found[:20]:
        where = f"{item['pfad']} → {item['archiv_eintrag']}" if item["archiv_eintrag"] else item["pfad"]
        more = t(" (+{} weitere Fundorte)", len(item["weitere_fundorte"])) if item["weitere_fundorte"] else ""
        print("  " + t("{:>3} Teile ({})  {}{}", item["anzahl_ids"], ", ".join(tr(a) for a in item["arten"]), where, more))
        if item["verwendet_von"]:
            print("        " + t("für: {}", ", ".join(item["verwendet_von"][:3])))
    if len(found) > 20:
        print("  " + t("… {} weitere im Bericht", len(found) - 20))
    _print_unreadable(unreadable)
    if restored is not None:
        _print_restored(cfg, restored, failed, skipped)
    elif found:
        print("\n" + t("Zurückholen ohne neue Suche: py -3 main.py restore   "
                       "(einzelne Funde auslassen: --ohne WickedWhims)"))

    from savegame_analyzer import analyze_usage
    import core
    if restored:
        mod_scan = _scan_mods(cfg)      # der Mods-Ordner hat sich geändert
    id_usage = {}
    usage = analyze_usage(mod_scan, saves, tray_folder=cfg.get("tray_folder"), progress=_progress,
                          id_usage=id_usage)
    conflicts = core.check_conflicts(cfg, mod_scan, id_usage, _progress)
    if restored:
        _print_conflicts(conflicts)
    _write_report(cfg, mod_scan, usage, saves, missing, info, conflicts=conflicts,
                  found={"dateien": found, "ordner": folders, "nicht_lesbar": unreadable,
                         "gefunden": n_found, "gesucht": len(parts)})
    return 0


def _print_unreadable(unreadable):
    if not unreadable:
        return
    sims = [u for u in unreadable if u.get("sims")]
    print("\n" + t("{} Archiv(e) konnten nicht durchsucht werden, davon {} mit Sims-Bezug:", len(unreadable), len(sims)))
    for u in sims[:15]:
        print(f"  {u['pfad']}  – {u['grund']}")
    if len(unreadable) > len(sims):
        print("  " + t("… {} weitere ohne erkennbaren Sims-Bezug (siehe Bericht)", len(unreadable) - len(sims)))


def _print_restored(cfg, restored, failed, skipped=None):
    import cc_finder
    print("\n" + t("{} Datei(en) zurückgeholt nach {}", len(restored),
                    os.path.join(cfg["mods_folder"], cc_finder.RESTORE_SUBFOLDER)))
    if skipped:
        print(t("{} Datei(en) nicht kopiert, damit nichts doppelt im Mods-Ordner landet:", len(skipped)))
        for name, reason in skipped[:10]:
            print(f"  {name} – {reason}")
    for name, reason in (failed or [])[:10]:
        print("  " + t("nicht geklappt: {} – {}", name, reason))
    if restored:
        print(t('Tipp: Mit "py -3 main.py analyze --all-saves" prüfst du, was jetzt noch fehlt.'))


def _latest_find_report(folder):
    import glob
    import json
    for path in sorted(glob.glob(os.path.join(folder, "report_*.json")), reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if (data.get("fundstellen") or {}).get("dateien"):
            return path, data
    return None, None


def _backup_before_restore(cfg, args):
    """Sichert den Mods-Ordner als ZIP, bevor etwas zurückgeholt wird. Gibt False bei Fehler zurück."""
    if getattr(args, "ohne_backup", False):
        return True
    from backup_manager import full_zip_backup
    print(t("Sichere zuerst den Mods-Ordner nach {} …", os.path.abspath(cfg["backup_folder"])))
    try:
        path = full_zip_backup(cfg["mods_folder"], cfg["backup_folder"])
    except OSError as e:
        print(t("Backup fehlgeschlagen ({}) – es wird nichts zurückgeholt.", e))
        return False
    print(t("Backup: {}", os.path.abspath(path)))
    return True


def cmd_restore(cfg, args):
    """Holt die Funde aus dem letzten Suchbericht zurück – ohne erneute Suche."""
    import json
    import tempfile
    import archive_tools
    import cc_finder
    if not _check_folder(cfg["mods_folder"], "Mods-Ordner"):
        return 1
    if args.bericht:
        path = args.bericht
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        path, data = _latest_find_report(cfg["report_folder"])
    found = ((data or {}).get("fundstellen") or {}).get("dateien") or []
    if not found:
        print(t('Kein Suchbericht mit Funden gefunden – zuerst "py -3 main.py find" ausführen.'))
        return 1
    print(t("Bericht: {} – {} Datei(en)", path, len(found)))
    if not _backup_before_restore(cfg, args):
        return 1
    tools = archive_tools.tools_from_config(cfg)
    temp_base = cfg.get("temp_folder") or None
    skipped = []
    with tempfile.TemporaryDirectory(prefix=cc_finder.TEMP_PREFIX, dir=temp_base) as work_dir:
        restored, failed = cc_finder.restore(found, cfg["mods_folder"], exclude=args.ohne or [], tools=tools,
                                             work_dir=work_dir, progress=_progress, skipped=skipped)
    _print_restored(cfg, restored, failed, skipped)
    return 0


def cmd_conflicts(cfg, args):
    """Prüft Konflikte genau (gleich/unterschiedlich, genutzt?) und sortiert Überflüssiges auf Wunsch aus."""
    from savegame_analyzer import find_saves, analyze_usage
    import core
    if not _check_folder(cfg["mods_folder"], "Mods-Ordner"):
        return 1
    mod_scan = _scan_mods(cfg)
    saves = find_saves(cfg["savegames_folder"])
    print(t("Gleiche mit {} Spielständen und der Bibliothek ab …", len(saves)))
    id_usage = {}
    analyze_usage(mod_scan, saves, tray_folder=cfg.get("tray_folder"), progress=_progress, id_usage=id_usage)
    result = core.check_conflicts(cfg, mod_scan, id_usage, _progress)
    _print_conflicts(result)
    if args.aufraeumen and (result["entfernbar"] or result.get("aufloesbar")):
        out = core.clean_conflicts(cfg, result)
        if out["verschoben"]:
            print("\n" + t("{} Datei(en) verschoben nach {}", len(out["verschoben"]), out["ordner"]))
            print(t("Es wurde nichts gelöscht – zum Rückgängigmachen einfach zurück in den Mods-Ordner schieben."))
        for name, count in out["bereinigt"]:
            print("  " + t("{} veraltete Doppel aus {} entfernt", count, name))
        if out["bereinigt"]:
            print(t("Originale der geänderten Pakete: {}", out["backup"]))
        for name, reason in out["fehler"]:
            print("  " + t("nicht geklappt: {} – {}", name, reason))
    return 0


def cmd_repair(cfg, args):
    """Prüft CC und Spielstände auf Schäden; mit --ausfuehren wird repariert, was sicher geht."""
    import core
    import repair
    if not _check_folder(cfg["mods_folder"], "Mods-Ordner"):
        return 1
    print(t("Prüfe CC-Dateien und Spielstände (gründlich – das dauert) …") if args.gruendlich
          else t("Prüfe CC-Dateien und Spielstände …"))
    items = core.check_health(cfg, deep=args.gruendlich, progress=_progress)
    broken = [it for it in items if it["zustand"] == repair.BROKEN]
    n_saves = sum(1 for it in items if it["typ"] == "Spielstand")
    print("\n" + t("{} CC-Dateien und {} Spielstände geprüft: {} beschädigt.", len(items) - n_saves, n_saves,
                    len(broken)))
    for it in broken:
        mark = t("reparierbar") if it["reparierbar"] else t("nicht reparierbar")
        print(f"  [{tr(it['typ'])}, {mark}] {it['datei']}")
        print(f"      {it['problem']}")
        print(f"      → {it['loesung']}")
    fixable = [it for it in broken if it["reparierbar"]]
    if not fixable:
        if broken:
            print("\n" + t("Nichts davon lässt sich reparieren – die Dateien neu herunterladen."))
        return 0
    if not args.ausfuehren:
        print("\n" + t("{} davon lassen sich reparieren: py -3 main.py repair --ausfuehren", len(fixable)))
        return 0
    backup_dir, results = core.repair_items(cfg, items, progress=_progress)
    print("\n" + t("Originale gesichert in {}", backup_dir))
    for name, ok, message in results:
        print(f"  {t('repariert') if ok else t('nicht geklappt')}: {name} – {message}")
    return 0


def cmd_backup(cfg, args):
    import core
    if args.target == "list":
        backups = core.list_backups(cfg)
        if not backups:
            print(t("Keine Backups in {}", cfg["backup_folder"]))
        for b in backups:
            print(f"  {b['zeit']:%d.%m.%Y %H:%M}  {tr(b['art_name']):22} {b['groesse'] / 1048576:8.1f} MB  {b['name']}")
        return 0
    if args.target == "restore":
        if not args.name:
            print(t('Welches Backup? Namen aus "py -3 main.py backup list" angeben.'))
            return 1
        try:
            out = core.restore_backup(cfg, args.name, overwrite=not args.nur_fehlendes, exact=args.genau,
                                      progress=_progress)
        except ValueError as e:
            print(e)
            return 1
        if len(out["kette"]) > 1:
            print(t("Eingespielt in dieser Reihenfolge: {}", " → ".join(out["kette"])))
        print(t("{} Datei(en) wiederhergestellt nach {}", out["wiederhergestellt"], ", ".join(out["ziele"]))
              + (t(", {} vorhandene nicht angefasst", out["uebersprungen"]) if out["uebersprungen"] else ""))
        if out["beiseite"]:
            print(t("{} Datei(en), die das Backup nicht kennt, liegen jetzt in {}", out["verschoben"], out["beiseite"]))
        return 0
    if args.target == "cleanup":
        doomed = core.cleanup_backups(cfg, dry_run=True)
        rules = cfg.get("backup_cleanup") or {}
        print(t("Regeln: höchstens {} Voll-Backups je Ordner, nichts älter als {} Tage; das neueste Voll-Backup "
                "bleibt immer.", rules.get("keep_last", 10), rules.get("max_age_days", 30)))
        if not doomed:
            print(t("Nichts aufzuräumen."))
            return 0
        for b in doomed:
            print(f"  {b['zeit']:%d.%m.%Y %H:%M}  {tr(b['art_name']):22} {b['groesse'] / 1048576:8.1f} MB  {b['name']}")
        if not args.ausfuehren:
            print("\n" + t("{} Backup(s) würden gelöscht – ausführen mit: py -3 main.py backup cleanup --ausfuehren",
                            len(doomed)))
            return 0
        removed, freed = core.cleanup_backups(cfg)
        print("\n" + t("{} Backup(s) gelöscht, {:.1f} MB frei.", len(removed), freed / 1048576))
        return 0
    source = cfg["mods_folder"] if args.target == "mods" else cfg["savegames_folder"]
    if not _check_folder(source, "Quellordner"):
        return 1
    mode = args.mode or cfg.get("backup_mode", "full")
    result = core.backup(cfg, args.target, mode, file_list=args.files)
    print(t("Backup ({}) erstellt: {}", mode, os.path.abspath(result)))
    return 0


def cmd_update(cfg, args):
    """Prüft auf GitHub, ob es eine neuere Version gibt; --laden lädt das ZIP herunter."""
    import core
    try:
        info = core.check_update()
    except (OSError, ValueError) as e:
        print(t("GitHub ist gerade nicht erreichbar: {}", e))
        return 1
    print(t("Installiert: {}   Neuestes Release: {}", info["aktuell"], info["neueste"] or "–"))
    if not info["neuer"]:
        print(t("SimVault ist aktuell."))
        return 0
    print("\n" + t("Neue Version {}: {}", info["neueste"], info["url"]) + "\n")
    print(info["notizen"].strip()[:3000])
    if args.laden:
        path = core.download_update(info, progress=_progress)
        print("\n" + t("Heruntergeladen: {}", path) + "\n"
              + t("Entpacken und den Inhalt über den alten Programmordner kopieren."))
    else:
        print("\n" + t('Herunterladen: py -3 main.py update --laden   (aus dem Quellcode aktualisierst du mit "git pull")'))
    return 0


def cmd_db(cfg, args):
    """Prüft die Verbindung zur eingestellten Datenbank (SQLite, MySQL/MariaDB, PostgreSQL)."""
    import database
    ok, message = database.test_connection(cfg["database"])
    print(message)
    return 0 if ok else 1


def cmd_install(cfg, args):
    """Installiert heruntergeladene CC (Datei oder Archiv, auch eine URL) – ohne Doppeltes, ohne Überschreiben."""
    import core
    import downloads
    if not _check_folder(cfg["mods_folder"], "Mods-Ordner"):
        return 1
    for target in args.dateien:
        if target.lower().startswith(("http://", "https://")):
            try:
                item, _items = core.download(cfg, target, progress=_progress)
            except Exception as e:
                print(t("{}: nicht heruntergeladen – {}", target, e))
                continue
            path = item["datei"]
            print(t("Heruntergeladen: {}", path))
        else:
            path = target
            if not os.path.isfile(path):
                print(t("Datei nicht gefunden: {}", path))
                continue
        result = core.install_download(cfg, path)
        print(f"\n{os.path.basename(path)}: {downloads.summary(result)}")
        for kind, dest in result["installiert"]:
            print(f"  + {tr(kind)}: {dest}")
        for name, reason in result["uebersprungen"]:
            print(f"  = {name} – {reason}")
        for name, reason in result["fehler"]:
            print(f"  ! {name} – {reason}")
    return 0


def _ask(prompt, default=""):
    shown = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{shown}: ").strip().strip('"')
    except EOFError:
        answer = ""
    return answer or default


def cmd_setup(cfg, args):
    """Fragt die wichtigsten Einstellungen ab und speichert sie in config.json."""
    import archive_tools
    raw = cfg_mod.load_config(args.config)
    print(t("SimVault einrichten – Enter übernimmt den Vorschlag in [Klammern].") + "\n")

    # 1. Sims-Ordner
    sims = _ask(t("1) Sims-4-Ordner (mit Mods, saves, Tray)"), raw.get("sims_folder") or cfg_mod.find_sims_folder())
    if sims and not os.path.isdir(sims):
        print("   " + t("Achtung: {} gibt es nicht – bitte später in config.json korrigieren.", sims))
    raw["sims_folder"] = sims

    # 2. Spielordner (optional)
    import game_locator
    print("\n" + t("2) Spielordner (die Installation – macht die Erkennung fehlender CC genau). Suche …"))
    found = game_locator.find_game_folders(deep=True)
    for i, c in enumerate(found, 1):
        print(f"   {i}) {game_locator.describe(c)}")
    if not found:
        print("   " + t("Keine Installation gefunden – Pfad von Hand eingeben oder mit '-' überspringen."))
    default = raw.get("game_folder") or (found[0]["pfad"] if found else "")
    game = _ask("   " + t("Nummer, eigener Pfad oder '-' für keinen"), default)
    if game.isdigit() and 1 <= int(game) <= len(found):
        game = found[int(game) - 1]["pfad"]
    if game not in ("", "-") and not game_locator.is_game_folder(game):
        print("   " + t("Achtung: In {} liegt kein Data\\Client – das ist vermutlich nicht die Installation.", game))
    raw["game_folder"] = "" if game == "-" else game

    # 3. Entpacker für RAR/7z
    tools = archive_tools.find_tools()
    print("\n" + t("3) Entpacker für RAR- und 7z-Archive bei der CC-Suche:"))
    for i, (kind, path) in enumerate(tools, 1):
        print(f"   {i}) {archive_tools.TOOL_NAMES[kind]}  ({path})")
    custom = len(tools) + 1
    print(f"   {custom}) " + t("eigenen Pfad angeben (7z.exe, UnRAR.exe oder tar.exe)"))
    print("   0) " + t("keinen – RAR/7z-Archive überspringen"))
    if not tools:
        print("   " + t("Es wurde kein Entpacker gefunden. Empfehlung: 7-Zip installieren (winget install 7zip.7zip)"))
    current = raw.get("extractor", "")
    default = "1" if tools else "0"
    if current.lower() == "none":
        default = "0"
    elif current:
        default = next((str(i) for i, (_k, p) in enumerate(tools, 1)
                        if os.path.normcase(p) == os.path.normcase(current)), str(custom))
    if tools and not any(k == "7z" for k, _p in tools):
        print("   " + t("Hinweis: Ohne 7-Zip lassen sich viele 7z-Archive nicht öffnen (UnRAR kann nur RAR, das\n"
                         "   Windows-tar keine LZMA-Komprimierung). Empfehlung: winget install 7zip.7zip"))
    choice = _ask("   " + t("Auswahl"), default)
    if choice == "0":
        raw["extractor"] = "none"
    elif choice.isdigit() and 1 <= int(choice) <= len(tools):
        raw["extractor"] = tools[int(choice) - 1][1]
    else:
        path = _ask("   " + t("Pfad zum Entpacker"), current if choice == str(custom) else choice)
        if path and os.path.isfile(path) and archive_tools.tool_kind(path):
            raw["extractor"] = path
        else:
            print("   " + t("Nicht nutzbar – es wird automatisch gesucht."))
            raw["extractor"] = ""

    # 4. Laufwerke
    yes, no = t("j"), t("n")
    drives = _ask("\n" + t("4) Bei der Suche auch alle weiteren Laufwerke (D:, E:, USB …) durchsuchen? (j/n)"),
                  yes if raw.get("search_drives", True) else no)
    raw["search_drives"] = drives.lower().startswith(("j", "y"))

    cfg_mod.save_config(raw, args.config)
    print("\n" + t("Gespeichert in {}", os.path.abspath(args.config)))
    return cmd_config(cfg_mod.resolve_paths(raw), args)


def _opt(de, en):
    """Option deutsch und englisch; in der Hilfe steht die Fassung der eingestellten Sprache vorne."""
    import i18n
    return (en, de) if i18n.language() == "en" else (de, en)


def build_parser():
    # Optionen gibt es deutsch und englisch (--aufraeumen = --clean …); die Hilfe folgt der eingestellten Sprache.
    p = argparse.ArgumentParser(prog="simvault", description=t("SimVault – Sims 4 CC-Analyse und Backup"))
    p.add_argument("--config", default="config.json", help=t("Pfad zur config.json"))
    p.add_argument("--lang", choices=["auto", "de", "en"], help=t("Sprache der Ausgabe (Standard: aus config.json)"))
    p.add_argument("-v", "--verbose", action="store_true", help=t("ausführliche Ausgabe"))
    sub = p.add_subparsers(dest="command")

    a = sub.add_parser("analyze", help=t("Mods mit Spielständen/Bibliothek abgleichen (Standard)"))
    a.add_argument("--save", nargs="+", help=t("bestimmte Spielstand-Datei(en)"))
    a.add_argument("--all-saves", action="store_true", help=t("alle Spielstände statt nur den neuesten"))
    a.add_argument("--no-tray", action="store_true", help=t("Bibliothek (Tray) nicht einbeziehen"))
    a.add_argument("--no-missing", action="store_true", help=t("keine Suche nach fehlender CC"))
    a.set_defaults(func=cmd_analyze)

    s = sub.add_parser("scan", help=t("nur den Mods-Ordner prüfen"))
    s.set_defaults(func=cmd_scan)

    b = sub.add_parser("backup", help=t("Backup von Mods oder Spielständen; list / restore NAME / cleanup"))
    b.add_argument("target", choices=["mods", "saves", "list", "restore", "cleanup"])
    b.add_argument("name", nargs="?", help=t("bei restore: Name des Backups (siehe backup list)"))
    b.add_argument(*_opt("--nur-fehlendes", "--only-missing"), dest="nur_fehlendes", action="store_true",
                   help=t("restore: vorhandene Dateien nicht überschreiben"))
    b.add_argument(*_opt("--genau", "--exact"), dest="genau", action="store_true",
                   help=t("restore: Ordner genau auf den Backup-Stand bringen (Übriges wird beiseitegelegt)"))
    b.add_argument(*_opt("--ausfuehren", "--apply"), dest="ausfuehren", action="store_true",
                   help=t("cleanup: wirklich löschen (sonst nur anzeigen)"))
    b.add_argument("--mode", choices=["full", "delta", "selective"])
    b.add_argument("--files", nargs="+", help=t("Dateien (relativ zum Ordner) für selective"))
    b.set_defaults(func=cmd_backup)

    f = sub.add_parser("find", help=t("fehlende CC auf dem PC suchen (Ordner und ZIP-Archive)"))
    f.add_argument("folders", nargs="*",
                   help=t("Suchordner (Standard: Downloads, Desktop, alte Mods-Ordner, Mod-Manager … und alle "
                          "weiteren Laufwerke)"))
    f.add_argument("--restore", action="store_true",
                   help=t("gefundene Pakete nach Mods/SimVault_wiederhergestellt kopieren"))
    f.add_argument(*_opt("--ganzer-pc", "--whole-pc"), dest="ganzer_pc", action="store_true",
                   help=t("auch das komplette Systemlaufwerk C: durchsuchen (dauert länger)"))
    f.add_argument(*_opt("--ohne-laufwerke", "--no-drives"), dest="ohne_laufwerke", action="store_true",
                   help=t("nur die Ordner durchsuchen, keine weiteren Laufwerke (D:, E: …)"))
    f.add_argument(*_opt("--ohne-backup", "--no-backup"), dest="ohne_backup", action="store_true",
                   help=t("bei --restore den Mods-Ordner vorher nicht sichern"))
    f.add_argument(*_opt("--ohne", "--skip"), dest="ohne", nargs="+", metavar="TEXT",
                   help=t("beim Zurückholen Funde auslassen, deren Datei/Fundort diesen Text enthält"))
    f.set_defaults(func=cmd_find)

    r = sub.add_parser("restore", help=t("Funde aus dem letzten Suchbericht in den Mods-Ordner zurückholen"))
    r.add_argument(*_opt("--ohne", "--skip"), dest="ohne", nargs="+", metavar="TEXT",
                   help=t("Funde auslassen, deren Datei/Fundort TEXT enthält"))
    r.add_argument(*_opt("--bericht", "--report"), dest="bericht", help=t("bestimmter Bericht (.json) statt des neuesten"))
    r.add_argument(*_opt("--ohne-backup", "--no-backup"), dest="ohne_backup", action="store_true", help=t("Mods-Ordner vorher nicht sichern"))
    r.set_defaults(func=cmd_restore)

    k = sub.add_parser("conflicts", help=t("Konflikte genau prüfen: gleich oder unterschiedlich, genutzt oder nicht"))
    k.add_argument(*_opt("--aufraeumen", "--clean"), dest="aufraeumen", action="store_true",
                   help=t("überflüssige Dateien (stecken komplett in anderen) aus dem Mods-Ordner aussortieren"))
    k.set_defaults(func=cmd_conflicts)

    rp = sub.add_parser("repair", help=t("CC und Spielstände auf Schäden prüfen und reparieren"))
    rp.add_argument(*_opt("--gruendlich", "--thorough"), dest="gruendlich", action="store_true",
                    help=t("jede Ressource entpacken (findet mehr, dauert länger)"))
    rp.add_argument(*_opt("--ausfuehren", "--apply"), dest="ausfuehren", action="store_true",
                    help=t("reparieren, was sich sicher reparieren lässt"))
    rp.set_defaults(func=cmd_repair)

    u = sub.add_parser("update", help=t("nach einer neueren SimVault-Version suchen"))
    u.add_argument(*_opt("--laden", "--download"), dest="laden", action="store_true", help=t("das neue Release (ZIP) herunterladen"))
    u.set_defaults(func=cmd_update)

    dbp = sub.add_parser("db", help=t("Verbindung zur Datenbank prüfen (SQLite, MySQL/MariaDB, PostgreSQL)"))
    dbp.set_defaults(func=cmd_db)

    ins = sub.add_parser("install", help=t("heruntergeladene CC installieren (Datei, Archiv oder URL)"))
    ins.add_argument("dateien", nargs="+", metavar=t("DATEI"),
                     help=t(".package, .ts4script, Bibliotheks-Datei, ZIP/RAR/7z oder URL"))
    ins.set_defaults(func=cmd_install)

    st = sub.add_parser("setup", help=t("einrichten: Ordner, Entpacker für RAR/7z, Laufwerke"))
    st.set_defaults(func=cmd_setup)

    c = sub.add_parser("config", help=t("verwendete Pfade anzeigen"))
    c.set_defaults(func=cmd_config)
    return p


def _choose_language(argv):
    """Sprache vor dem Aufbau der Hilfe festlegen: --lang, sonst ui_language aus der config.json, sonst System."""
    import i18n
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default="config.json")
    pre.add_argument("--lang")
    known, _rest = pre.parse_known_args(argv)
    code = known.lang
    if not code:
        try:
            import json
            with open(known.config, encoding="utf-8") as f:
                code = json.load(f).get("ui_language")
        except (OSError, ValueError, AttributeError):
            code = None
    return i18n.set_language(code or "auto", qt=False)


def _safe_output():
    """Zeichen, die die Windows-Konsole nicht kennt (z. B. → bei umgeleiteter Ausgabe), dürfen nie zum Absturz führen."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _safe_output()
    _choose_language(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    first_run = not os.path.exists(args.config)
    cfg = cfg_mod.resolve_paths(cfg_mod.load_config(args.config))
    if first_run and args.command != "setup":
        print(t('Neue config.json angelegt. Tipp: Mit "py -3 main.py setup" richtest du SimVault ein '
                "(Ordner, Entpacker für RAR/7z, Laufwerke).") + "\n")
    if not args.command:
        args = parser.parse_args(["--config", args.config] + (["-v"] if args.verbose else [])
                                 + (["--lang", args.lang] if args.lang else []) + ["analyze"])
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
