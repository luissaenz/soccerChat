import os
import json
import logging
import httpx
from bot.prompts import build_system_prompt
from bot.db import get_all_players, get_recent_matches, get_recent_comments, update_player_elo, get_player_by_name, add_player, add_match, get_all_aliases
from bot.elo import update_elos_for_match

logger = logging.getLogger(__name__)

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


ANALYZE_PROMPT = """Sos Mister, el DT sarcástico del grupo de fútbol.

Analizá el siguiente comentario de un miembro del grupo. Tu tarea:
1. Determiná si el comentario habla sobre el desempeño de algún jugador (positivo o negativo).
2. Si detectás que se habla de alguien, respondé con un JSON así:
   {{"adjustments": [{{"player": "NombreExacto", "delta": 5, "reason": "razón breve"}}], "reply": "tu comentario con humor"}}
   - delta: entre -10 y +10. Positivo si lo elogian, negativo si lo bardean por jugar mal.
   - player: debe ser el nombre EXACTO de la lista de jugadores registrados.
   - reply: respuesta breve y sarcástica (1-2 oraciones máximo).
3. Si el comentario NO tiene nada que ver con el desempeño de nadie, respondé:
   {{"adjustments": [], "reply": ""}}

IMPORTANTE: Respondé SOLO el JSON, sin markdown, sin texto adicional.

Jugadores registrados: {players}

Comentarios recientes para contexto: {recent_comments}

Comentario de [{author}]: {comment}"""


async def analyze_comment(comment: str, author: str) -> dict | None:
    """
    Analiza un comentario del grupo. Si la IA detecta que habla de rendimiento,
    retorna ajustes de ELO y una respuesta con humor.
    Retorna None si no hay nada relevante o hay error.
    """
    players = await get_all_players()
    if not players:
        return None

    player_names = [p["name"] for p in players]
    recent = await get_recent_comments(10)
    recent_lines = [f"  {c['player_name']}: \"{c['content']}\"" for c in recent[:5]]

    prompt = ANALYZE_PROMPT.format(
        players=", ".join(player_names),
        recent_comments="\n".join(recent_lines) if recent_lines else "Ninguno",
        author=author,
        comment=comment,
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/soccer-chat-bot",
        "X-Title": "SoccerChat DT Bot",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.7,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()
            # Limpiar posible markdown wrapping
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(raw)

            if not result.get("adjustments"):
                return None

            # Aplicar ajustes de ELO
            applied = []
            for adj in result["adjustments"]:
                player = await get_player_by_name(adj["player"])
                if player and abs(adj["delta"]) <= 10:
                    new_elo = player["elo"] + adj["delta"]
                    await update_player_elo(player["id"], round(new_elo, 1), increment_matches=False)
                    applied.append(adj)
                    logger.info(f"ELO ajustado: {adj['player']} {adj['delta']:+d} ({adj['reason']})")

            if applied and result.get("reply"):
                return {"adjustments": applied, "reply": result["reply"]}
            return None

    except (json.JSONDecodeError, KeyError, httpx.HTTPError) as e:
        logger.warning(f"Error analizando comentario: {e}")
        return None


MATCH_DETECT_PROMPT = """Sos un parser de resultados de fútbol. Tu ÚNICA tarea es detectar si el mensaje contiene información de un partido jugado (formación de equipos + resultado).

Si el mensaje describe un partido con equipos y resultado, respondé con este JSON:
{{"is_match": true, "team_a": ["Nombre1", "Nombre2", ...], "team_b": ["Nombre3", "Nombre4", ...], "score_a": 3, "score_b": 2, "team_a_label": "Claro", "team_b_label": "Oscuro", "reply": "comentario breve y sarcástico sobre el resultado como DT"}}

Reglas:
- team_a y team_b deben contener los NOMBRES de los jugadores (no apodos del equipo).
- Si un nombre tiene un alias conocido, usá el nombre CANÓNICO (el principal registrado).
- Si dice "ganó Claro" o "ganó Oscuro" o similar, asegurate de que el score refleje eso.
- Si no hay score explícito pero dice quién ganó, poné 1-0.
- Si dice "ganó por X goles" sin score exacto, poné X-0.
- reply: debe ser sarcástico, en español rioplatense, breve (1-2 oraciones).

Si el mensaje NO describe un partido, respondé:
{{"is_match": false}}

IMPORTANTE: Respondé SOLO el JSON, sin markdown, sin texto adicional.

Jugadores registrados: {players}
Aliases conocidos: {aliases}

Mensaje de [{author}]: {message}"""


async def detect_match_result(message: str, author: str) -> dict | None:
    """
    Detecta si un mensaje contiene un resultado de partido.
    Si lo detecta, registra el partido, auto-registra jugadores nuevos,
    actualiza ELOs y retorna info para responder.
    Retorna None si no es un partido.
    """
    players = await get_all_players()
    player_names = [p["name"] for p in players] if players else []
    aliases = await get_all_aliases()
    aliases_str = ", ".join(f"{a['alias']}→{a['canonical_name']}" for a in aliases) if aliases else "Ninguno"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/soccer-chat-bot",
        "X-Title": "SoccerChat DT Bot",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": MATCH_DETECT_PROMPT.format(
            author=author,
            message=message,
            players=", ".join(player_names) if player_names else "Ninguno registrado aún",
            aliases=aliases_str,
        )}],
        "max_tokens": 400,
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(raw)

            if not result.get("is_match"):
                return None

            team_a = result["team_a"]
            team_b = result["team_b"]
            score_a = int(result["score_a"])
            score_b = int(result["score_b"])

            # Auto-registrar jugadores nuevos
            for name in team_a + team_b:
                existing = await get_player_by_name(name)
                if not existing:
                    await add_player(name=name)

            # Registrar partido y actualizar ELOs
            match_id = await add_match(team_a, team_b, score_a, score_b)
            await update_elos_for_match(team_a, team_b, score_a, score_b)

            label_a = result.get("team_a_label", "A")
            label_b = result.get("team_b_label", "B")
            reply = result.get("reply", "Partido registrado.")

            return {
                "match_id": match_id,
                "team_a": team_a,
                "team_b": team_b,
                "score_a": score_a,
                "score_b": score_b,
                "label_a": label_a,
                "label_b": label_b,
                "reply": reply,
            }

    except (json.JSONDecodeError, KeyError, httpx.HTTPError) as e:
        logger.warning(f"Error detectando partido: {e}")
        return None
