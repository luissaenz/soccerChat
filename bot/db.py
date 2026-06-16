import aiosqlite
import json
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "./data/soccer.db")


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    db = await get_db()
    await db.executescript("""
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
    """)
    await db.commit()
    await db.close()


# --- Players ---

async def add_player(name: str, telegram_username: Optional[str] = None, telegram_id: Optional[int] = None) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO players (name, telegram_username, telegram_id) VALUES (?, ?, ?)",
        (name, telegram_username, telegram_id)
    )
    await db.commit()
    player_id = cursor.lastrowid
    await db.close()
    return player_id


async def get_player_by_name(name: str) -> Optional[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM players WHERE LOWER(name) = LOWER(?)", (name,))
    row = await cursor.fetchone()
    await db.close()
    if row:
        return dict(row)
    return None


async def get_player_by_telegram_id(telegram_id: int) -> Optional[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM players WHERE telegram_id = ?", (telegram_id,))
    row = await cursor.fetchone()
    await db.close()
    if row:
        return dict(row)
    return None


async def get_all_players() -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM players ORDER BY elo DESC")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


async def update_player_elo(player_id: int, new_elo: float, increment_matches: bool = True):
    db = await get_db()
    if increment_matches:
        await db.execute(
            "UPDATE players SET elo = ?, matches_played = matches_played + 1 WHERE id = ?",
            (new_elo, player_id)
        )
    else:
        await db.execute("UPDATE players SET elo = ? WHERE id = ?", (new_elo, player_id))
    await db.commit()
    await db.close()


# --- Matches ---

async def add_match(team_a: list[str], team_b: list[str], score_a: int, score_b: int, notes: Optional[str] = None, date: Optional[str] = None) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO matches (team_a, team_b, score_a, score_b, notes, date) VALUES (?, ?, ?, ?, ?, ?)",
        (json.dumps(team_a), json.dumps(team_b), score_a, score_b, notes, date or datetime.now().isoformat())
    )
    await db.commit()
    match_id = cursor.lastrowid
    await db.close()
    return match_id


async def get_recent_matches(limit: int = 10) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM matches ORDER BY date DESC LIMIT ?", (limit,))
    rows = await cursor.fetchall()
    await db.close()
    results = []
    for r in rows:
        d = dict(r)
        d["team_a"] = json.loads(d["team_a"])
        d["team_b"] = json.loads(d["team_b"])
        results.append(d)
    return results


async def get_all_matches() -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM matches ORDER BY date DESC")
    rows = await cursor.fetchall()
    await db.close()
    results = []
    for r in rows:
        d = dict(r)
        d["team_a"] = json.loads(d["team_a"])
        d["team_b"] = json.loads(d["team_b"])
        results.append(d)
    return results


# --- Comments ---

async def add_comment(player_telegram_id: int, player_name: str, content: str, match_id: Optional[int] = None) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO comments (match_id, player_telegram_id, player_name, content) VALUES (?, ?, ?, ?)",
        (match_id, player_telegram_id, player_name, content)
    )
    await db.commit()
    comment_id = cursor.lastrowid
    await db.close()
    return comment_id


async def get_recent_comments(limit: int = 20) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM comments ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


async def get_comments_for_match(match_id: int) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM comments WHERE match_id = ? ORDER BY created_at", (match_id,))
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]
