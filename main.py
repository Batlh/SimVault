# main.py

def main():
    # 1. Savegame laden und analysieren
    from savegame_analyzer import analyze_savegame

    savegame_path = "Pfad/zum/Savegame"
    cc_ids = analyze_savegame(savegame_path)

    # 2. Mods-Ordner scannen
    from mod_folder_scanner import scan_mods_folder

    mods_folder = "Pfad/zum/Mods-Ordner"
    existing_mods = scan_mods_folder(mods_folder)

    # 3. Fehlende CCs bestimmen
    missing_cc = set(cc_ids) - set(existing_mods)

    # 4. Alternative CCs online suchen
    from cc_searcher import search_alternatives

    cc_alternatives = search_alternatives(missing_cc)

    # 5. Report generieren
    from report_generator import generate_report

    generate_report(missing_cc, cc_alternatives)

    # 6. (Optional) GUI starten
    from gui_interface import start_gui

    start_gui()

if __name__ == "__main__":
    main()
