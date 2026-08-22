"""
Build Database
===============
Loads parsed_changes.json (produced by parser.py) into a SQLite database.
This is the "real" data store the API will actually query -- unlike the
JSON file, a database means the API doesn't have to reload and re-parse
7000+ records into memory on every request, and it's the same kind of
store you'd point a hosted backend at later (SQLite files work fine for
small projects; migrating to Postgres later just means swapping the
connection, not rewriting queries).

Run this once whenever parsed_changes.json changes (a fresh scrape, a
newly-added patch, a parser fix) to rebuild patches.db from scratch.
"""

import json
import sqlite3
from pathlib import Path

INPUT_PATH = Path("parsed_changes.json")
DB_PATH = Path("patches.db")

SCHEMA = """
CREATE TABLE changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    champion TEXT NOT NULL,
    ability TEXT NOT NULL,
    patch TEXT NOT NULL,
    change_type TEXT NOT NULL,
    stat TEXT,
    old_value TEXT,
    new_value TEXT,
    effect_name TEXT,
    description TEXT
);
CREATE INDEX idx_champion ON changes(champion);
CREATE INDEX idx_patch ON changes(patch);
"""


def build_database() -> None:
    records = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(records)} records from {INPUT_PATH}")

    if DB_PATH.exists():
        DB_PATH.unlink()  # rebuild from scratch each time, avoids stale/duplicate rows

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    rows = [
        (
            r["champion"], r["ability"], r["patch"], r["change_type"],
            r.get("stat"), r.get("old_value"), r.get("new_value"),
            r.get("effect_name"), r.get("description"),
        )
        for r in records
    ]
    conn.executemany(
        """INSERT INTO changes
           (champion, ability, patch, change_type, stat, old_value, new_value, effect_name, description)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM changes").fetchone()[0]
    champions = conn.execute("SELECT COUNT(DISTINCT champion) FROM changes").fetchone()[0]
    patches = conn.execute("SELECT COUNT(DISTINCT patch) FROM changes").fetchone()[0]
    conn.close()

    print(f"Built {DB_PATH}: {count} rows, {champions} champions, {patches} patches")


if __name__ == "__main__":
    build_database()
