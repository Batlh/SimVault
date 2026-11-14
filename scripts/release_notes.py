"""Erzeugt die Release-Beschreibung: CHANGELOG-Abschnitt der Version + Commits seit dem letzten Release.

Aufruf: python scripts/release_notes.py v0.5.0 Batlh/SimVault > notes.md
"""
import re
import subprocess
import sys


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else ""


def changelog_section(version):
    try:
        text = open("CHANGELOG.md", encoding="utf-8").read()
    except OSError:
        return ""
    pattern = rf"^## \[{re.escape(version.lstrip('v'))}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    m = re.search(pattern, text, re.S | re.M)
    return m.group(1).strip() if m else ""


def main():
    tag, repo = sys.argv[1], sys.argv[2]
    end = tag if git("rev-parse", "-q", "--verify", f"refs/tags/{tag}") else "HEAD"
    prev = git("describe", "--tags", "--abbrev=0", f"{end}^")
    rng = f"{prev}..{end}" if prev else end
    commits = git("log", rng, "--no-merges", "--pretty=format:%h\t%s")

    out = [changelog_section(tag) or "_Kein Changelog-Eintrag für diese Version._", "", "### Commits"]
    for line in commits.splitlines():
        h, _, subject = line.partition("\t")
        out.append(f"- [`{h}`](https://github.com/{repo}/commit/{h}) {subject}")
    if prev:
        out += ["", f"**Alle Änderungen:** https://github.com/{repo}/compare/{prev}...{tag}"]
    out += ["", "### Installation", "`SimVault-Windows.zip` herunterladen, entpacken und `SimVault.exe` starten."]
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
