# Modul: database.py
# Funktion: Speichert jede Analyse zusätzlich in einer Datenbank – SQLite (Standard) oder für Fortgeschrittene
#           MySQL/MariaDB bzw. PostgreSQL.
#
# Einstellungen in config.json, Abschnitt "database":
#   "type": "sqlite" | "mysql" | "postgresql"
#   "sqlite_path": "simvault_data.db"
#   "mysql":      {"host": "localhost", "port": 3306, "user": "…", "password": "…", "database": "simvault"}
#   "postgresql": {"host": "localhost", "port": 5432, "user": "…", "password": "…", "database": "simvault"}
# Statt das Passwort in config.json zu schreiben, kann es in der Umgebungsvariable SIMVAULT_DB_PASSWORD stehen.
#
# MySQL/PostgreSQL brauchen einen Treiber, der nicht mitgeliefert wird (die Kommandozeile bleibt ohne Zusatzpakete):
#   MySQL/MariaDB: pip install pymysql            (oder mysql-connector-python)
#   PostgreSQL:    pip install "psycopg[binary]"  (oder psycopg2-binary)
# Alle Datenbanken bekommen dieselben Tabellen: scans, mod_files, issues, missing_cc.

import os
import json
import logging

log = logging.getLogger(__name__)

TYPES = ("sqlite", "mysql", "postgresql")


class DatabaseError(Exception):
    pass


def _table_sql(id_column, text="TEXT"):
    return [
        f"CREATE TABLE IF NOT EXISTS scans (id {id_column}, created {text}, mods_folder {text}, saves {text}, "
        f"summary {text})",
        f"CREATE TABLE IF NOT EXISTS mod_files (scan_id INTEGER, path {text}, category {text}, status {text}, "
        f"saves {text}, tray_items INTEGER, size BIGINT, resources INTEGER)",
        f"CREATE TABLE IF NOT EXISTS issues (scan_id INTEGER, severity {text}, kind {text}, message {text}, "
        f"files {text})",
        f"CREATE TABLE IF NOT EXISTS missing_cc (scan_id INTEGER, id {text}, kind {text}, uses INTEGER, "
        f"used_by {text}, sources {text})",
    ]


class Adapter:
    name = ""
    placeholder = "?"
    id_column = "INTEGER PRIMARY KEY AUTOINCREMENT"
    returning = False                   # INSERT … RETURNING id (PostgreSQL)

    def __init__(self, conn):
        self.conn = conn

    def create_tables(self, cur):
        for sql in _table_sql(self.id_column):
            cur.execute(sql)

    def insert_scan(self, cur, values):
        p = ", ".join([self.placeholder] * 4)
        sql = f"INSERT INTO scans (created, mods_folder, saves, summary) VALUES ({p})"
        if self.returning:
            cur.execute(sql + " RETURNING id", values)
            return cur.fetchone()[0]
        cur.execute(sql, values)
        return cur.lastrowid

    def insert_many(self, cur, table, rows, width):
        if rows:
            p = ", ".join([self.placeholder] * width)
            cur.executemany(f"INSERT INTO {table} VALUES ({p})", rows)


class SQLiteAdapter(Adapter):
    name = "SQLite"


class MySQLAdapter(Adapter):
    name = "MySQL/MariaDB"
    placeholder = "%s"
    id_column = "INTEGER AUTO_INCREMENT PRIMARY KEY"

    def create_tables(self, cur):
        for sql in _table_sql(self.id_column, "LONGTEXT"):
            cur.execute(sql + " DEFAULT CHARSET=utf8mb4")


class PostgresAdapter(Adapter):
    name = "PostgreSQL"
    placeholder = "%s"
    id_column = "SERIAL PRIMARY KEY"
    returning = True


def _settings(db, key, port):
    s = dict(db.get(key) or {})
    s.setdefault("host", "localhost")
    s.setdefault("port", port)
    s.setdefault("database", "simvault")
    password = os.environ.get("SIMVAULT_DB_PASSWORD")
    if password:
        s["password"] = password
    return s


def connect(db):
    """Verbindung nach den Einstellungen db (Abschnitt "database" der config.json). Gibt einen Adapter zurück."""
    kind = (db.get("type") or "sqlite").lower()
    if kind in ("postgres", "pgsql"):
        kind = "postgresql"
    if kind == "mysql" or (kind == "sqlite" and (db.get("mysql") or {}).get("enabled")):   # alte Schreibweise
        s = _settings(db, "mysql", 3306)
        try:
            import pymysql
            conn = pymysql.connect(host=s["host"], port=int(s["port"]), user=s.get("user", ""),
                                   password=s.get("password", ""), database=s["database"], charset="utf8mb4")
        except ImportError:
            try:
                import mysql.connector
            except ImportError:
                raise DatabaseError("Für MySQL fehlt der Treiber: pip install pymysql") from None
            conn = mysql.connector.connect(host=s["host"], port=int(s["port"]), user=s.get("user", ""),
                                           password=s.get("password", ""), database=s["database"])
        return MySQLAdapter(conn)
    if kind == "postgresql":
        s = _settings(db, "postgresql", 5432)
        params = dict(host=s["host"], port=int(s["port"]), user=s.get("user", ""),
                      password=s.get("password", ""), dbname=s["database"])
        try:
            import psycopg
            conn = psycopg.connect(**params)
        except ImportError:
            try:
                import psycopg2
            except ImportError:
                raise DatabaseError('Für PostgreSQL fehlt der Treiber: pip install "psycopg[binary]"') from None
            conn = psycopg2.connect(**params)
        return PostgresAdapter(conn)
    if kind != "sqlite":
        raise DatabaseError(f"Unbekannte Datenbank „{kind}“ – möglich: {', '.join(TYPES)}")
    import sqlite3
    path = db.get("sqlite_path") or "simvault_data.db"
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    return SQLiteAdapter(sqlite3.connect(path))


def write_scan(db, now, summary, issues, data_rows, missing=None):
    """Schreibt eine Analyse in die Datenbank. Gibt die Nummer des Scans zurück."""
    adapter = connect(db)
    conn = adapter.conn
    try:
        cur = conn.cursor()
        adapter.create_tables(cur)
        scan_id = adapter.insert_scan(cur, (now.isoformat(timespec="seconds"), summary["mods_ordner"],
                                            json.dumps(summary["spielstaende"]),
                                            json.dumps(summary, ensure_ascii=False, default=str)))
        adapter.insert_many(cur, "mod_files", [
            (scan_id, d["datei"], d["kategorie"], d["status"], ", ".join(d["spielstaende"]),
             d["tray_eintraege"], d["groesse_bytes"], d["ressourcen"]) for d in data_rows], 8)
        adapter.insert_many(cur, "issues", [
            (scan_id, i["schwere"], i["art"], i["meldung"], json.dumps(i["dateien"], ensure_ascii=False))
            for i in issues], 5)
        adapter.insert_many(cur, "missing_cc", [
            (scan_id, m["id"], m["art"], m["anzahl"], json.dumps(m["verwendet_von"], ensure_ascii=False),
             ", ".join(m["quellen"])) for m in (missing or [])], 6)
        conn.commit()
        return scan_id
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def test_connection(db):
    """Prüft die Verbindung. Gibt (ok, Meldung) zurück."""
    try:
        adapter = connect(db)
    except Exception as e:
        return False, str(e)
    try:
        cur = adapter.conn.cursor()
        adapter.create_tables(cur)
        adapter.conn.commit()
        return True, f"{adapter.name}: Verbindung steht, Tabellen sind angelegt."
    except Exception as e:
        return False, f"{adapter.name}: {e}"
    finally:
        adapter.conn.close()
