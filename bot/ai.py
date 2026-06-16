import os
import json
import httpx
from bot.prompts import build_system_prompt
from bot.db import get_all_players, get_recent_matches, get_recent_comments

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def build_context() -> str:
    players = await get_all_players()
    matches = await get_recent_matches(10)
    comments = await get_recent_comments(20)

    parts = []

    if players:
        ranking = "\n".join(
            f"  - {p['name']}: ELO {p['elo']:.0f} ({p['matches_played']} partidos)"
            for p in players
        )
        parts.append(f"RANKING DE JUGADORES:\n{ranking}")

    if matches:
        match_lines = []
        for m in matches:
            team_a_str = ", ".join(m["team_a"])
            team_b_str = ", ".join(m["team_b"])
            match_lines.append(f"  - {m['date'][:10]}: [{team_a_str}] {m['score_a']} - {m['score_b']} [{team_b_str}]")
        parts.append(f"ÚLTIMOS PARTIDOS:\n" + "\n".join(match_lines))

    if comments:
        comment_lines = [f"  - {c['player_name']}: \"{c['content']}\"" for c in comments[:10]]
        parts.append(f"COMENTARIOS RECIENTES:\n" + "\n".join(comment_lines))

    return "\n\n".join(parts) if parts else "No hay datos todavía. Recién arrancamos."


async def chat(user_message: str, user_name: str = "Alguien") -> str:
    context = await build_context()
    system_prompt = build_system_prompt(context)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/soccer-chat-bot",
        "X-Title": "SoccerChat DT Bot",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"[{user_name}]: {user_message}"},
        ],
        "max_tokens": 500,
        "temperature": 0.9,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        return f"⚠️ Error del modelo ({e.response.status_code}). Debe ser que hasta la IA se cansó de este grupo."
    except Exception as e:
        return f"⚠️ Error inesperado: {str(e)[:100]}"
