# main.py – Einstiegspunkt von SimVault (Kommandozeile)
#
# Beispiele:
#   python main.py                      Analyse: Mods-Ordner + neuester Spielstand + Bibliothek
#   python main.py analyze --all-saves  alle Spielstände einbeziehen
#   python main.py analyze --save "C:\...\Slot_00000002.save"
#   python main.py scan                 nur Mods-Ordner prüfen (ohne Spielstand)
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
                "backup_folder", "report_folder"):
        path = cfg.get(key, "")
        state = "ok" if path and os.path.isdir(path) else "fehlt"
        print(f"{key:18} {state:6} {path}")
    print(f"\nKonfigurationsdatei: {os.path.abspath(args.config)}")
    return 0


def _scan_mods(cfg):
    from mod_folder_scanner import scan_mods_folder
    print(f"Scanne Mods-Ordner: {cfg['mods_folder']}")
    return scan_mods_folder(cfg["mods_folder"], progress=lambda i, n: _progress(f"{i}/{n} Dateien"))


def _print_summary(mod_scan, usage):
    from collections import Counter
    print(f"\n{len(mod_scan.mods)} Mod-Dateien gefunden.")
    for cat, n in Counter(m.category for m in mod_scan.mods).most_common():
        print(f"  {cat:18} {n}")
    if usage is not None:
        print("\nNutzung:")
        for status, n in Counter(r["status"] for r in usage).most_common():
            print(f"  {status:18} {n}")
    if mod_scan.issues:
        print(f"\n{len(mod_scan.issues)} Problem(e):")
        for issue in mod_scan.issues:
            print(f"  [{issue.severity}] {issue.kind}: {len(issue.files)} Datei(en)")


def _write_report(cfg, mod_scan, usage=None, saves=None):
    from report_generator import generate_report
    files = generate_report(mod_scan, usage, saves,
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
    missing = [s for s in saves if not os.path.isfile(s)]
    if missing:
        print("Spielstand nicht gefunden: " + ", ".join(missing))
        return 1
    if not saves:
        print(f"Kein Spielstand gefunden in {cfg['savegames_folder']} – es wird nur die Bibliothek geprüft.")

    mod_scan = _scan_mods(cfg)
    print("Lese Spielstände und Bibliothek …")
    tray = None if args.no_tray else cfg.get("tray_folder")
    usage = analyze_usage(mod_scan, saves, tray_folder=tray, progress=_progress)
    _print_summary(mod_scan, usage)
    _write_report(cfg, mod_scan, usage, saves)
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
    a.set_defaults(func=cmd_analyze)

    s = sub.add_parser("scan", help="nur den Mods-Ordner prüfen")
    s.set_defaults(func=cmd_scan)

    b = sub.add_parser("backup", help="Backup von Mods oder Spielständen")
    b.add_argument("target", choices=["mods", "saves"])
    b.add_argument("--mode", choices=["full", "delta", "selective"])
    b.add_argument("--files", nargs="+", help="Dateien (relativ zum Ordner) für selective")
    b.set_defaults(func=cmd_backup)

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
