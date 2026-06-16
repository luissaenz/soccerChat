import os
import json
import logging
import httpx
from bot.db import get_player_stats, get_leaderboard_stats, get_all_matches, get_all_players
from bot.elo import K_FACTOR, goal_diff_multiplier

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

ANALYST_SYSTEM_PROMPT = """Sos un analista deportivo profesional de fútbol amateur. Tu nombre es "El Analista".
Tu estilo es serio, preciso, basado en datos. Hablás en español rioplatense pero sin humor — solo datos y conclusiones.

Tu trabajo:
- Explicar ELOs y qué significan los números.
- Dar análisis táctico basado en estadísticas disponibles.
- Comparar jugadores con datos concretos.
- Identificar tendencias (rachas, mejoras, caídas).
- Recomendar formaciones basadas en data.

Formato:
- Usá emojis de estadísticas: 📊📈📉🎯⚡🔥
- Presentá datos en listas claras y ordenadas.
- Si no hay suficiente data, decilo honestamente.
- No inventes datos — solo usá lo que te dan.

Sistema ELO:
- Base: 1000 puntos iniciales.
- K-Factor: {k_factor}.
- La diferencia de goles aplica un multiplicador suave (log2): 1 gol = 1.0x, 3 goles ≈ 1.3x, 8 goles ≈ 1.6x.
- Victoria contra equipo con ELO mayor da más puntos.
- Derrota contra equipo con ELO menor quita más puntos.
""".format(k_factor=K_FACTOR)


async def build_stats_context() -> str:
    """Construye contexto estadístico completo para el Analista."""
    leaderboard = await get_leaderboard_stats()
    matches = await get_all_matches()

    parts = []

    if leaderboard:
        parts.append("📊 RANKING ACTUAL:")
        for i, p in enumerate(leaderboard, 1):
            parts.append(f"  {i}. {p['name']} — ELO: {p['elo']} | {p['matches']}PJ | {p['wins']}W | WR: {p['winrate']}%")

    if matches:
        parts.append(f"\n📋 HISTORIAL ({len(matches)} partidos):")
        for m in matches[:10]:
            team_a_str = ", ".join(m["team_a"])
            team_b_str = ", ".join(m["team_b"])
            parts.append(f"  {m['date'][:10]}: [{team_a_str}] {m['score_a']}-{m['score_b']} [{team_b_str}]")

    return "\n".join(parts) if parts else "No hay datos todavía."


async def format_player_report(player_name: str) -> str:
    """Genera un reporte estadístico de un jugador sin IA."""
    stats = await get_player_stats(player_name)
    if not stats:
        return f"No encontré datos para '{player_name}'."

    p = stats["player"]
    streak_icon = {"W": "🔥", "L": "❄️", "D": "➡️"}.get(stats["streak_type"], "")
    streak_text = f"{streak_icon} {stats['streak']}{stats['streak_type']}" if stats["streak"] > 0 else "—"

    teammates_str = ", ".join(f"{name} ({count})" for name, count in stats["top_teammates"]) or "—"
    rivals_str = ", ".join(f"{name} ({count})" for name, count in stats["top_rivals"]) or "—"

    return (
        f"📊 *FICHA DE {p['name'].upper()}*\n\n"
        f"🏆 ELO: *{p['elo']}*\n"
        f"⚽ Partidos: {stats['total']} ({stats['wins']}W / {stats['draws']}D / {stats['losses']}L)\n"
        f"🎯 Winrate: {stats['winrate']}%\n"
        f"📈 Racha: {streak_text}\n"
        f"🤝 Compañeros frecuentes: {teammates_str}\n"
        f"⚔️ Rivales frecuentes: {rivals_str}"
    )


async def format_full_leaderboard() -> str:
    """Genera tabla de posiciones con stats completas sin IA."""
    lb = await get_leaderboard_stats()
    if not lb:
        return "No hay datos de jugadores todavía."

    medals = ["🥇", "🥈", "🥉"]
    lines = ["📊 *TABLA DE POSICIONES*\n"]
    for i, p in enumerate(lb):
        icon = medals[i] if i < 3 else "  "
        lines.append(
            f"{icon} {i+1}. *{p['name']}* — ELO: {p['elo']} | "
            f"{p['matches']}PJ | {p['wins']}W | WR: {p['winrate']}%"
        )

    return "\n".join(lines)


async def analyst_chat(question: str) -> str:
    """Usa la IA con el perfil Analista para responder preguntas de stats."""
    context = await build_stats_context()

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/soccer-chat-bot",
        "X-Title": "SoccerChat Analyst",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
            {"role": "user", "content": f"DATOS DISPONIBLES:\n{context}\n\nPREGUNTA: {question}"},
        ],
        "max_tokens": 600,
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error en analyst_chat: {e}")
        return "Error al consultar al Analista. Intentá de nuevo."
