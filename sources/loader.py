# Modul: sources/loader.py
# Funktion: Lädt die mitgelieferten Quellen und alle Erweiterungen aus den Erweiterungs-Ordnern.
#
# Erweiterungs-Ordner (alle werden durchsucht):
#   - "plugins" neben dem Programm bzw. im SimVault-Ordner
#   - der Benutzerordner: Windows %APPDATA%\SimVault\plugins, sonst ~/.config/simvault/plugins
#   - zusätzliche Ordner aus config.json ("plugin_folders")
#
# Zwei Arten von Erweiterungen:
#   *.json – einfache Link-Quelle(n), ohne Programmieren:
#            {"id": "simsdom", "name": "SimsDom", "search_url": "https://…/search?q={query}"}
#            (auch eine Liste solcher Einträge ist erlaubt)
#   *.py   – Voll-Quellen: Klassen, die von sources.base.Source erben, oder eine Liste SOURCES.
#            Optional: REQUIRES_API = 1 (Mindestversion der Schnittstelle)
#
# Eine Erweiterung mit derselben id wie eine mitgelieferte Quelle ersetzt diese.
# Fehler in einer Erweiterung brechen nichts ab – sie werden gesammelt und angezeigt.

import os
import sys
import json
import logging
import importlib.util

from .base import API_VERSION, Source, LinkSource
from .builtin import builtin_sources

log = logging.getLogger(__name__)


def app_dir():
    """Ordner des Programms (bei der .exe der Ordner der .exe)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_plugin_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "SimVault", "plugins")
    return os.path.join(os.path.expanduser("~"), ".config", "simvault", "plugins")


def plugin_dirs(cfg=None):
    dirs = [os.path.join(app_dir(), "plugins"), user_plugin_dir()]
    dirs += list((cfg or {}).get("plugin_folders") or [])
    seen, result = set(), []
    for d in dirs:
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen:
            seen.add(key)
            result.append(d)
    return result


def _from_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data if isinstance(data, list) else [data]
    sources = []
    for entry in entries:
        missing = [k for k in ("id", "name", "search_url") if not entry.get(k)]
        if missing:
            raise ValueError(f"Eintrag ohne {', '.join(missing)}")
        if "{query}" not in entry["search_url"]:
            raise ValueError(f"search_url von '{entry['id']}' enthält kein {{query}}")
        sources.append(LinkSource(
            id=str(entry["id"]).strip().lower(), name=entry["name"], template=entry["search_url"],
            homepage=entry.get("homepage", ""), description=entry.get("description", ""),
            adult=bool(entry.get("adult", False)), needs_login=bool(entry.get("needs_login", False)),
            login_url=entry.get("login_url", ""), enabled_by_default=bool(entry.get("enabled", True))))
    return sources


def _from_python(path):
    name = "simvault_plugin_" + os.path.splitext(os.path.basename(path))[0].replace("-", "_").replace(" ", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = getattr(module, "REQUIRES_API", API_VERSION)
    if required > API_VERSION:
        raise ValueError(f"braucht Schnittstelle {required}, SimVault hat {API_VERSION} – SimVault aktualisieren")
    if hasattr(module, "SOURCES"):
        sources = list(module.SOURCES)
    else:
        sources = [obj() for obj in vars(module).values()
                   if isinstance(obj, type) and issubclass(obj, Source)
                   and obj.__module__ == module.__name__ and obj.id]
    for source in sources:
        if not isinstance(source, Source) or not source.id or not source.name:
            raise ValueError("Quelle ohne id/name oder nicht von Source abgeleitet")
    return sources


def load_sources(cfg=None):
    """Gibt (quellen, fehler) zurück. quellen: Liste von Source, fehler: [(Datei, Meldung)]."""
    by_id = {}
    for source in builtin_sources():
        source.origin = "mitgeliefert"
        by_id[source.id] = source
    errors = []
    for folder in plugin_dirs(cfg):
        if not os.path.isdir(folder):
            continue
        for filename in sorted(os.listdir(folder)):
            path = os.path.join(folder, filename)
            low = filename.lower()
            if filename.startswith(("_", ".")) or not low.endswith((".json", ".py")):
                continue
            try:
                found = _from_json(path) if low.endswith(".json") else _from_python(path)
            except Exception as e:  # eine kaputte Erweiterung darf nichts anderes stören
                errors.append((path, f"{type(e).__name__}: {e}"))
                log.warning("Erweiterung %s nicht geladen: %s", path, e)
                continue
            for source in found:
                source.origin = path
                by_id[source.id] = source
    return list(by_id.values()), errors


def is_enabled(source, cfg=None):
    return bool(((cfg or {}).get("sources_enabled") or {}).get(source.id, source.enabled_by_default))


def enabled_sources(cfg=None):
    sources, _errors = load_sources(cfg)
    return [s for s in sources if is_enabled(s, cfg)]
