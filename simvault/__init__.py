# Paket: simvault – das eigentliche Programm.
#   app/       Ablauf und Einstellungen: core, config, version, updater, Sprachen (i18n)
#   analysis/  Dateien lesen und prüfen: DBPF-Pakete, Spielstände, fehlende CC, Konflikte, Reparatur, Vorschaubilder
#   finder/    CC auf dem PC finden: Suche, Archive, Spielordner
#   web/       Internet: Abrufe, Downloads, Anmeldungen, Quellen (CC-Seiten)
#   storage/   Ablegen: Berichte, Backups, Datenbank
#   gui/       Programmfenster (Qt/PySide6)
# Gestartet wird über main.py (Kommandozeile) bzw. simvault_gui.py (Programmfenster) im Hauptordner.
import os
import sys


def project_dir():
    """Programmordner: bei der .exe der Ordner der .exe, sonst der Hauptordner des Repositorys."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
