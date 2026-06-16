import libsql_experimental as libsql
import json
import os
from datetime import datetime
from typing import Optional

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

_conn = None


def get_db():
    global _conn
    if _conn is None:
        if TURSO_DATABASE_URL:
            _conn = libsql.connect(
                database=TURSO_DATABASE_URL,
                auth_token=TURSO_AUTH_TOKEN,
            )
        else:
            os.makedirs("./data", exist_ok=True)
            _conn = libsql.connect(database="./data/soccer.db")
    return _conn


def _row_to_dict(cursor, row) -> dict:
    """Convert a row tuple to dict using cursor description."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


async def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            telegram_username TEXT,
            telegram_id INTEGER,
            elo REAL DEFAULT 1000.0,
            matches_played INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT DEFAULT (datetime('now')),
            team_a TEXT NOT NULL,
            team_b TEXT NOT NULL,
            score_a INTEGER NOT NULL,
            score_b INTEGER NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER,
            player_telegram_id INTEGER,
            player_name TEXT,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (match_id) REFERENCES matches(id)
        );

        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            alias TEXT NOT NULL,
            FOREIGN KEY (player_id) REFERENCES players(id)
        );
    """)
    db.commit()


# --- Players ---

async def add_player(name: str, telegram_username: Optional[str] = None, telegram_id: Optional[int] = None) -> int:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO players (name, telegram_username, telegram_id) VALUES (?, ?, ?)",
        (name, telegram_username, telegram_id)
    )
    db.commit()
    return cursor.lastrowid


async def get_player_by_name(name: str) -> Optional[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM players WHERE LOWER(name) = LOWER(?)", (name,))
    row = cursor.fetchone()
    if row:
        return _row_to_dict(cursor, row)
    # Check aliases
    cursor = db.execute(
        "SELECT p.* FROM players p JOIN aliases a ON p.id = a.player_id WHERE LOWER(a.alias) = LOWER(?)",
        (name,)
    )
    row = cursor.fetchone()
    if row:
        return _row_to_dict(cursor, row)
    return None


async def get_player_by_telegram_id(telegram_id: int) -> Optional[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM players WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    if row:
        return _row_to_dict(cursor, row)
    return None


async def get_all_players() -> list[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM players ORDER BY elo DESC")
    rows = cursor.fetchall()
    return [_row_to_dict(cursor, r) for r in rows]


async def update_player_elo(player_id: int, new_elo: float, increment_matches: bool = True):
    db = get_db()
    if increment_matches:
        db.execute(
            "UPDATE players SET elo = ?, matches_played = matches_played + 1 WHERE id = ?",
            (new_elo, player_id)
        )
    else:
        db.execute("UPDATE players SET elo = ? WHERE id = ?", (new_elo, player_id))
    db.commit()


# --- Matches ---

async def add_match(team_a: list[str], team_b: list[str], score_a: int, score_b: int, notes: Optional[str] = None, date: Optional[str] = None) -> int:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO matches (team_a, team_b, score_a, score_b, notes, date) VALUES (?, ?, ?, ?, ?, ?)",
        (json.dumps(team_a), json.dumps(team_b), score_a, score_b, notes, date or datetime.now().isoformat())
    )
    db.commit()
    return cursor.lastrowid


async def get_recent_matches(limit: int = 10) -> list[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM matches ORDER BY date DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = _row_to_dict(cursor, r)
        d["team_a"] = json.loads(d["team_a"])
        d["team_b"] = json.loads(d["team_b"])
        results.append(d)
    return results


async def get_all_matches() -> list[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM matches ORDER BY date DESC")
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = _row_to_dict(cursor, r)
        d["team_a"] = json.loads(d["team_a"])
        d["team_b"] = json.loads(d["team_b"])
        results.append(d)
    return results


# --- Comments ---

async def add_comment(player_telegram_id: int, player_name: str, content: str, match_id: Optional[int] = None) -> int:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO comments (match_id, player_telegram_id, player_name, content) VALUES (?, ?, ?, ?)",
        (match_id, player_telegram_id, player_name, content)
    )
    db.commit()
    return cursor.lastrowid


async def get_recent_comments(limit: int = 20) -> list[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM comments ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    return [_row_to_dict(cursor, r) for r in rows]


async def get_comments_for_match(match_id: int) -> list[dict]:
    db = get_db()
    cursor = db.execute("SELECT * FROM comments WHERE match_id = ? ORDER BY created_at", (match_id,))
    rows = cursor.fetchall()
    return [_row_to_dict(cursor, r) for r in rows]


# --- Aliases ---

async def add_alias(player_id: int, alias: str):
    db = get_db()
    db.execute("INSERT INTO aliases (player_id, alias) VALUES (?, ?)", (player_id, alias))
    db.commit()


async def get_aliases_for_player(player_id: int) -> list[str]:
    db = get_db()
    cursor = db.execute("SELECT alias FROM aliases WHERE player_id = ?", (player_id,))
    rows = cursor.fetchall()
    return [r[0] for r in rows]


async def get_all_aliases() -> list[dict]:
    db = get_db()
    cursor = db.execute(
        "SELECT a.alias, p.name as canonical_name FROM aliases a JOIN players p ON a.player_id = p.id"
    )
    rows = cursor.fetchall()
    return [_row_to_dict(cursor, r) for r in rows]
