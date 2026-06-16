import libsql_client
import json
import os
from datetime import datetime
from typing import Optional

TURSO_DATABASE_URL = "https://soccer-chat-ld-saenz.aws-us-west-2.turso.io"
TURSO_AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODE1NzczMDksImlkIjoiMDE5ZWNlNDctYjIwMS03MGNhLWJiYWMtZThjYmQ0OWEwMzExIiwicmlkIjoiMGRkYzA3YzUtZWM2Zi00NzdhLWJjYTYtNDkxOTljMzZhMTQ5In0.XzrJ1tMkRR6nd2wK8WylAITd7wO-p8M3mqAj9wX1idP9VCg7DXZKrPqHACrxvBVeNpATUKL94O2NHW_FomZRAQ"


def _get_url():
    return os.getenv("TURSO_DATABASE_URL", TURSO_DATABASE_URL)


def _get_token():
    return os.getenv("TURSO_AUTH_TOKEN", TURSO_AUTH_TOKEN)


def _rs_to_dicts(rs) -> list[dict]:
    """Convert a ResultSet to a list of dicts."""
    if not rs.rows:
        return []
    columns = rs.columns
    return [dict(zip(columns, row)) for row in rs.rows]


def _rs_first(rs) -> Optional[dict]:
    """Get first row as dict or None."""
    dicts = _rs_to_dicts(rs)
    return dicts[0] if dicts else None


async def _execute(sql: str, args=None):
    """Execute a single statement and return the ResultSet."""
    async with libsql_client.create_client(
        url=_get_url(),
        auth_token=_get_token(),
    ) as client:
        if args:
            return await client.execute(sql, args)
        return await client.execute(sql)


async def _batch(statements: list):
    """Execute multiple statements in a batch."""
    async with libsql_client.create_client(
        url=_get_url(),
        auth_token=_get_token(),
    ) as client:
        return await client.batch(statements)


async def init_db():
    stmts = [
        """CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            telegram_username TEXT,
            telegram_id INTEGER,
            elo REAL DEFAULT 1000.0,
            matches_played INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT DEFAULT (datetime('now')),
            team_a TEXT NOT NULL,
            team_b TEXT NOT NULL,
            score_a INTEGER NOT NULL,
            score_b INTEGER NOT NULL,
            notes TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER,
            player_telegram_id INTEGER,
            player_name TEXT,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (match_id) REFERENCES matches(id)
        )""",
        """CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            alias TEXT NOT NULL,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )""",
    ]
    await _batch(stmts)


# --- Players ---

async def add_player(name: str, telegram_username: Optional[str] = None, telegram_id: Optional[int] = None) -> int:
    rs = await _execute(
        "INSERT INTO players (name, telegram_username, telegram_id) VALUES (?, ?, ?)",
        [name, telegram_username, telegram_id]
    )
    return rs.last_insert_rowid


async def get_player_by_name(name: str) -> Optional[dict]:
    rs = await _execute("SELECT * FROM players WHERE LOWER(name) = LOWER(?)", [name])
    result = _rs_first(rs)
    if result:
        return result
    # Check aliases
    rs = await _execute(
        "SELECT p.* FROM players p JOIN aliases a ON p.id = a.player_id WHERE LOWER(a.alias) = LOWER(?)",
        [name]
    )
    return _rs_first(rs)


async def get_player_by_telegram_id(telegram_id: int) -> Optional[dict]:
    rs = await _execute("SELECT * FROM players WHERE telegram_id = ?", [telegram_id])
    return _rs_first(rs)


async def get_all_players() -> list[dict]:
    rs = await _execute("SELECT * FROM players ORDER BY elo DESC")
    return _rs_to_dicts(rs)


async def update_player_elo(player_id: int, new_elo: float, increment_matches: bool = True):
    if increment_matches:
        await _execute(
            "UPDATE players SET elo = ?, matches_played = matches_played + 1 WHERE id = ?",
            [new_elo, player_id]
        )
    else:
        await _execute("UPDATE players SET elo = ? WHERE id = ?", [new_elo, player_id])


# --- Matches ---

async def add_match(team_a: list[str], team_b: list[str], score_a: int, score_b: int, notes: Optional[str] = None, date: Optional[str] = None) -> int:
    rs = await _execute(
        "INSERT INTO matches (team_a, team_b, score_a, score_b, notes, date) VALUES (?, ?, ?, ?, ?, ?)",
        [json.dumps(team_a), json.dumps(team_b), score_a, score_b, notes, date or datetime.now().isoformat()]
    )
    return rs.last_insert_rowid


async def get_recent_matches(limit: int = 10) -> list[dict]:
    rs = await _execute("SELECT * FROM matches ORDER BY date DESC LIMIT ?", [limit])
    results = []
    for d in _rs_to_dicts(rs):
        d["team_a"] = json.loads(d["team_a"])
        d["team_b"] = json.loads(d["team_b"])
        results.append(d)
    return results


async def get_all_matches() -> list[dict]:
    rs = await _execute("SELECT * FROM matches ORDER BY date DESC")
    results = []
    for d in _rs_to_dicts(rs):
        d["team_a"] = json.loads(d["team_a"])
        d["team_b"] = json.loads(d["team_b"])
        results.append(d)
    return results


# --- Comments ---

async def add_comment(player_telegram_id: int, player_name: str, content: str, match_id: Optional[int] = None) -> int:
    rs = await _execute(
        "INSERT INTO comments (match_id, player_telegram_id, player_name, content) VALUES (?, ?, ?, ?)",
        [match_id, player_telegram_id, player_name, content]
    )
    return rs.last_insert_rowid


async def get_recent_comments(limit: int = 20) -> list[dict]:
    rs = await _execute("SELECT * FROM comments ORDER BY created_at DESC LIMIT ?", [limit])
    return _rs_to_dicts(rs)


async def get_comments_for_match(match_id: int) -> list[dict]:
    rs = await _execute("SELECT * FROM comments WHERE match_id = ? ORDER BY created_at", [match_id])
    return _rs_to_dicts(rs)


# --- Aliases ---

async def add_alias(player_id: int, alias: str):
    await _execute("INSERT INTO aliases (player_id, alias) VALUES (?, ?)", [player_id, alias])


async def get_aliases_for_player(player_id: int) -> list[str]:
    rs = await _execute("SELECT alias FROM aliases WHERE player_id = ?", [player_id])
    return [row[0] for row in rs.rows] if rs.rows else []


async def get_all_aliases() -> list[dict]:
    rs = await _execute(
        "SELECT a.alias, p.name as canonical_name FROM aliases a JOIN players p ON a.player_id = p.id"
    )
    return _rs_to_dicts(rs)
