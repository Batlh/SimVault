# Übergang für Erweiterungen (plugins/): Die Quellen liegen jetzt in simvault/web/sources.
# Ältere Erweiterungen schreiben noch „from sources.base import Source“ – das leitet hierher weiter und
# liefert genau dieselben Module (kein zweites Exemplar). Bleibt mindestens bis SimVault 1.0.
import sys

from simvault.web import sources as _sources
from simvault.web.sources import base, builtin, loader, sites  # noqa: F401

sys.modules[__name__] = _sources
for _name in ("base", "builtin", "loader", "sites"):
    sys.modules[f"{__name__}.{_name}"] = sys.modules[f"simvault.web.sources.{_name}"]
