# Paket: sources – CC-Quellen (Webseiten) und das Erweiterungssystem dafür.
# Siehe base.py (Schnittstelle), builtin.py (mitgelieferte Quellen), loader.py (Erweiterungen laden).

from .base import API_VERSION, Source, LinkSource, SearchResult
from .loader import load_sources, enabled_sources, is_enabled, plugin_dirs, user_plugin_dir

__all__ = ["API_VERSION", "Source", "LinkSource", "SearchResult", "load_sources", "enabled_sources",
           "is_enabled", "plugin_dirs", "user_plugin_dir"]
