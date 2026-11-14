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
#   python main.py backup mods          Backup des Mods-Ordners (Modus aus config.json)
#   python main.py backup saves --mode delta
#   python main.py config               zeigt die verwendeten Pfade

import os
import sys
import argparse
import logging

import config as cfg_mod


def _setup_logging(verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")


def _progress(msg):
    print(f"  … {msg}", flush=True)


def _check_folder(path, label):
    if not path or not os.path.isdir(path):
        print(f"{label} nicht gefunden: {path or '(nicht gesetzt)'}")
        print("Bitte den Pfad in config.json eintragen (sims_folder oder den einzelnen Ordner).")
        return False
    return True


def cmd_config(cfg, args):
    for key in ("sims_folder", "mods_folder", "savegames_folder", "tray_folder",
                "game_folder", "backup_folder", "report_folder"):
        path = cfg.get(key, "")
        state = "ok" if path and os.path.isdir(path) else "fehlt"
        print(f"{key:18} {state:6} {path}")
    print(f"\nKonfigurationsdatei: {os.path.abspath(args.config)}")
    return 0


def _scan_mods(cfg):
    from mod_folder_scanner import scan_mods_folder
    print(f"Scanne Mods-Ordner: {cfg['mods_folder']}")
    return scan_mods_folder(cfg["mods_folder"], progress=lambda i, n: _progress(f"{i}/{n} Dateien"))


def _print_summary(mod_scan, usage, missing=None):
    from collections import Counter
    print(f"\n{len(mod_scan.mods)} Mod-Dateien gefunden.")
    for cat, n in Counter(m.category for m in mod_scan.mods).most_common():
        print(f"  {cat:18} {n}")
    if usage is not None:
        print("\nNutzung:")
        for status, n in Counter(r["status"] for r in usage).most_common():
            print(f"  {status:18} {n}")
    if missing is not None:
        parts = missing["teile"]
        if parts:
            print(f"\nFehlende CC: {len(parts)} verschiedene Teile/Objekte")
            for m in parts[:10]:
                print(f"  {m['id']}  {m['art'][:28]:28} {m['anzahl']:>4}×  {', '.join(m['verwendet_von'][:2])}")
            if len(parts) > 10:
                print(f"  … {len(parts) - 10} weitere im Bericht")
            if missing["bibliothek"]:
                print(f"\nBibliotheks-Einträge mit fehlender CC: {len(missing['bibliothek'])}")
                for h in missing["bibliothek"][:10]:
                    by = f" von {h['ersteller']}" if h["ersteller"] else ""
                    print(f"  {len(h['fehlend']):>3} fehlend  {h['name']}{by}")
        else:
            print("\nFehlende CC: keine gefunden")
    if mod_scan.issues:
        print(f"\n{len(mod_scan.issues)} Problem(e):")
        for issue in mod_scan.issues:
            print(f"  [{issue.severity}] {issue.kind}: {len(issue.files)} Datei(en)")


def _write_report(cfg, mod_scan, usage=None, saves=None, missing=None, missing_info=None, found=None):
    from report_generator import generate_report
    files = generate_report(mod_scan, usage, saves, missing=missing, missing_info=missing_info, found=found,
                            output_dir=cfg["report_folder"],
                            db_path=cfg["database"].get("sqlite_path"),
                            formats=cfg["report_formats"],
                            app_name=cfg["branding"].get("app_name", "SimVault"))
    print("\nBerichte:")
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
        print("Spielstand nicht gefunden: " + ", ".join(missing_files))
        return 1
    if not saves:
        print(f"Kein Spielstand gefunden in {cfg['savegames_folder']} – es wird nur die Bibliothek geprüft.")

    mod_scan = _scan_mods(cfg)
    print("Lese Spielstände und Bibliothek …")
    tray = None if args.no_tray else cfg.get("tray_folder")
    usage = analyze_usage(mod_scan, saves, tray_folder=tray, progress=_progress)

    missing = missing_info = None
    if not args.no_missing:
        missing, missing_info = _find_missing(cfg, mod_scan, saves, tray)

    _print_summary(mod_scan, usage, missing)
    _write_report(cfg, mod_scan, usage, saves, missing, missing_info)
    if missing and missing["teile"]:
        print('\nTipp: Mit "python main.py find" suchst du die fehlende CC auf deinem PC '
              "(Downloads, alte Mods-Ordner, ZIP-Archive).")
    return 0


def _find_missing(cfg, mod_scan, saves, tray):
    from missing_cc import find_missing, index_game_content
    known = set(mod_scan.id_lookup())
    game = cfg.get("game_folder")
    if game and os.path.isdir(game):
        print(f"Lese Spielinhalte aus {game} (beim ersten Mal etwas länger) …")
        known |= index_game_content(game, cache_path=cfg.get("game_cache", "game_ids_cache.json"),
                                    progress=_progress)
        info = f"Abgleich mit Mods-Ordner und Spielordner ({game})"
    else:
        info = ("Abgleich mit dem Mods-Ordner; Spielordner nicht gefunden – "
                "EA-Inhalte werden an ihren kleineren IDs erkannt")
    return find_missing(saves, tray, known, progress=_progress), info


def cmd_find(cfg, args):
    from savegame_analyzer import find_saves
    import cc_finder
    if not _check_folder(cfg["mods_folder"], "Mods-Ordner"):
        return 1
    folders = cc_finder.search_locations(cfg, args.folders, drives=not args.ohne_laufwerke,
                                         whole_pc=args.ganzer_pc)
    if not folders:
        print("Keine Suchordner gefunden. Ordner angeben: python main.py find \"D:\\Alte Mods\"")
        return 1

    mod_scan = _scan_mods(cfg)
    saves = find_saves(cfg["savegames_folder"])          # alle Spielstände
    print(f"Ermittle fehlende CC aus {len(saves)} Spielständen und der Bibliothek …")
    missing, info = _find_missing(cfg, mod_scan, saves, cfg.get("tray_folder"))
    parts = missing["teile"]
    if not parts:
        print("Es fehlt keine CC – nichts zu suchen. 🎉")
        return 0

    print(f"{len(parts)} fehlende Teile. Durchsuche:")
    for f in folders:
        print(f"  {f}")
    wanted = {int(p["id"], 16) for p in parts}
    hits, unreadable = cc_finder.search(folders, wanted, exclude=[cfg["mods_folder"]], progress=_progress)
    found, n_found = cc_finder.summarize(hits, parts)

    print(f"\nGefunden: {n_found} von {len(parts)} fehlenden Teilen in {len(found)} Datei(en).")
    for item in found[:20]:
        where = f"{item['pfad']} → {item['archiv_eintrag']}" if item["archiv_eintrag"] else item["pfad"]
        more = f" (+{len(item['weitere_fundorte'])} weitere Fundorte)" if item["weitere_fundorte"] else ""
        print(f"  {item['anzahl_ids']:>3} Teile ({', '.join(item['arten'])})  {where}{more}")
        if item["verwendet_von"]:
            print(f"        für: {', '.join(item['verwendet_von'][:3])}")
    if len(found) > 20:
        print(f"  … {len(found) - 20} weitere im Bericht")
    if unreadable:
        print(f"\n{len(unreadable)} Archiv(e) konnten nicht durchsucht werden (.rar/.7z/defekt) – "
              "bitte entpacken und erneut suchen:")
        for path in unreadable[:10]:
            print(f"  {path}")

    if found and args.restore:
        import cc_finder as cf
        created = cf.restore(found, cfg["mods_folder"], exclude=args.ohne or [])
        print(f"\n{len(created)} Datei(en) zurückgeholt nach "
              f"{os.path.join(cfg['mods_folder'], cf.RESTORE_SUBFOLDER)}")
    elif found:
        print('\nZum Zurückholen in den Mods-Ordner: python main.py find --restore '
              '(einzelne Funde auslassen: --ohne WickedWhims)')

    _write_report(cfg, mod_scan, None, saves, missing, info,
                  found={"dateien": found, "ordner": folders, "nicht_lesbar": unreadable,
                         "gefunden": n_found, "gesucht": len(parts)})
    return 0


def cmd_backup(cfg, args):
    from backup_manager import backup_manager
    source = cfg["mods_folder"] if args.target == "mods" else cfg["savegames_folder"]
    if not _check_folder(source, "Quellordner"):
        return 1
    mode = args.mode or cfg.get("backup_mode", "full")
    result = backup_manager(mode, source, cfg["backup_folder"], file_list=args.files)
    print(f"Backup ({mode}) erstellt: {os.path.abspath(result)}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="simvault", description="SimVault – Sims 4 CC-Analyse und Backup")
    p.add_argument("--config", default="config.json", help="Pfad zur config.json")
    p.add_argument("-v", "--verbose", action="store_true", help="ausführliche Ausgabe")
    sub = p.add_subparsers(dest="command")

    a = sub.add_parser("analyze", help="Mods mit Spielständen/Bibliothek abgleichen (Standard)")
    a.add_argument("--save", nargs="+", help="bestimmte Spielstand-Datei(en)")
    a.add_argument("--all-saves", action="store_true", help="alle Spielstände statt nur den neuesten")
    a.add_argument("--no-tray", action="store_true", help="Bibliothek (Tray) nicht einbeziehen")
    a.add_argument("--no-missing", action="store_true", help="keine Suche nach fehlender CC")
    a.set_defaults(func=cmd_analyze)

    s = sub.add_parser("scan", help="nur den Mods-Ordner prüfen")
    s.set_defaults(func=cmd_scan)

    b = sub.add_parser("backup", help="Backup von Mods oder Spielständen")
    b.add_argument("target", choices=["mods", "saves"])
    b.add_argument("--mode", choices=["full", "delta", "selective"])
    b.add_argument("--files", nargs="+", help="Dateien (relativ zum Ordner) für selective")
    b.set_defaults(func=cmd_backup)

    f = sub.add_parser("find", help="fehlende CC auf dem PC suchen (Ordner und ZIP-Archive)")
    f.add_argument("folders", nargs="*",
                   help="Suchordner (Standard: Downloads, Desktop, alte Mods-Ordner, Mod-Manager … und alle "
                        "weiteren Laufwerke)")
    f.add_argument("--restore", action="store_true",
                   help="gefundene Pakete nach Mods/SimVault_wiederhergestellt kopieren")
    f.add_argument("--ganzer-pc", action="store_true",
                   help="auch das komplette Systemlaufwerk C: durchsuchen (dauert länger)")
    f.add_argument("--ohne-laufwerke", action="store_true",
                   help="nur die Ordner durchsuchen, keine weiteren Laufwerke (D:, E: …)")
    f.add_argument("--ohne", nargs="+", metavar="TEXT",
                   help="beim Zurückholen Funde auslassen, deren Datei/Fundort diesen Text enthält")
    f.set_defaults(func=cmd_find)

    c = sub.add_parser("config", help="verwendete Pfade anzeigen")
    c.set_defaults(func=cmd_config)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    cfg = cfg_mod.resolve_paths(cfg_mod.load_config(args.config))
    if not args.command:
        args = parser.parse_args(["--config", args.config] + (["-v"] if args.verbose else []) + ["analyze"])
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
