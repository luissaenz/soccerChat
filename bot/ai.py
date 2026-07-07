import os
import re
import json
import random
import logging
from datetime import datetime
import httpx
from bot.prompts import build_system_prompt
from bot.db import (
    get_all_players, get_recent_matches, get_recent_comments,
    update_player_elo, get_player_by_name, add_match, get_all_aliases,
    add_elo_adjustment, get_adjustment_abs_sum_today,
)
from bot.elo import update_elos_for_match
from bot.humor import CARGADAS_MAL, HALAGOS, FRASES_EMPATE, FRASES_VICTORIA, FRASES_DERROTA

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Cap de |delta| acumulado por jugador por día vía comentarios.
# Evita que el grupo infle/hunda un ELO a fuerza de spam.
DAILY_ADJUSTMENT_CAP = 15
MAX_SINGLE_DELTA = 10


async def _post_llm(messages: list[dict], max_tokens: int, temperature: float, json_mode: bool = False) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/soccer-chat-bot",
        "X-Title": "SoccerChat DT Bot",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def _strip_code_fences(raw: str) -> str:
    """Fallback para modelos que ignoran response_format y devuelven ```json ... ```."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return raw


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
        parts.append(f"ÚLTIMOS PARTIDOS (los {len(matches)} más recientes):\n" + "\n".join(match_lines))

    if comments:
        comment_lines = [f"  - {c['player_name']}: \"{c['content'][:200]}\"" for c in comments[:10]]
        parts.append(f"COMENTARIOS RECIENTES:\n" + "\n".join(comment_lines))

    return "\n\n".join(parts) if parts else "No hay datos todavía. Recién arrancamos."


async def chat(user_message: str, user_name: str = "Alguien", reply_context: str | None = None) -> str:
    context = await build_context()
    system_prompt = build_system_prompt(context, datetime.now().strftime("%Y-%m-%d"))

    user_content = f"[{user_name}]: {user_message}"
    if reply_context:
        user_content = (
            f"(El mensaje responde a esto que dijiste antes: \"{reply_context[:300]}\")\n{user_content}"
        )

    try:
        return await _post_llm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=500,
            temperature=0.9,
        )
    except httpx.HTTPStatusError as e:
        return f"⚠️ Error del modelo ({e.response.status_code}). Debe ser que hasta la IA se cansó de este grupo."
    except Exception as e:
        return f"⚠️ Error inesperado: {str(e)[:100]}"


# ---------------------------------------------------------------------------
# Clasificador unificado: partido / comentario de rendimiento / nada
# Una sola llamada LLM por mensaje, con pre-filtro barato que evita la mayoría.
# Usa .replace() en vez de .format() para no tener que escapar las llaves JSON.
# ---------------------------------------------------------------------------

CLASSIFY_PROMPT = """Sos un clasificador de mensajes de un grupo de Telegram de fútbol amateur. Analizá el mensaje y clasificalo en UNO de tres tipos. Respondé SOLO con un JSON válido, sin markdown ni texto extra.

TIPO "match" — el mensaje informa un partido YA JUGADO (equipos y/o resultado):
{"type": "match", "team_a": ["Nombre1", ...], "team_b": ["Nombre2", ...], "score_a": 3, "score_b": 2, "team_a_label": "Claro", "team_b_label": "Oscuro", "unknown_names": [], "question": null}

TIPO "performance" — comentario sobre cómo jugó OTRO jugador del grupo (elogio o crítica):
{"type": "performance", "adjustments": [{"player": "NombreCanonico", "delta": 5, "reason": "razón breve"}]}

TIPO "none" — cualquier otra cosa:
{"type": "none"}

REGLAS PARA "match":
- team_a y team_b llevan los nombres CANÓNICOS de la lista de jugadores registrados. Resolvé diminutivos, apodos y variaciones usando la lista de jugadores y aliases (ej: "Facu" → "Facundo", "Gonza" → "Gonzalo", "Dani" → "Daniel").
- Si el mensaje lista jugadores bajo encabezados ("Equipo oscuro:", "Team claro", etc.), cada sección es un equipo. Los nombres pueden ir uno por línea o separados por comas.
- Nombre que NO podés resolver con certeza a un jugador registrado → agregalo a unknown_names y escribí en question una pregunta breve pidiendo aclaración. Si resolvés todos, unknown_names es [] y question es null.
- Scores: si hay números explícitos en el mensaje, usalos SIEMPRE. "ganó X por N goles" significa que X tiene score N y el rival 0. Si solo dice quién ganó, sin números, usá 1-0. El equipo que el mensaje dice que ganó SIEMPRE tiene el score mayor.
- team_a_label y team_b_label: cómo el mensaje llama a cada equipo ("Claro", "Oscuro", etc.). Si no tienen nombre, usá "A" y "B".

REGLAS PARA "performance":
- delta entre -10 y +10. Positivo si lo elogian, negativo si lo critican por jugar mal.
- Clasificá como "none" si: el autor habla de SÍ MISMO (autoelogio o autocrítica), es sarcasmo o ironía evidente, es un deseo o hipótesis ("ojalá juegue bien"), habla de fútbol profesional o de alguien NO registrado.
- player debe ser el nombre canónico registrado, resolviendo apodos con la lista de aliases.

EJEMPLOS:

Mensaje: "Equipo oscuro:\n1. Facu\n2. Korea\n3. Dani\nEquipo claro:\n1. Gonza\n2. Esteban\n3. Luis\nGanó el oscuro por 8 goles"
Respuesta: {"type": "match", "team_a": ["Facundo", "Korea", "Daniel"], "team_b": ["Gonzalo", "Esteban", "Luis"], "score_a": 8, "score_b": 0, "team_a_label": "Oscuro", "team_b_label": "Claro", "unknown_names": [], "question": null}

Mensaje: "jugamos 5 a 3, ganamos con Pedro contra Carlos y el Tucu" (y "Tucu" no aparece en jugadores ni aliases)
Respuesta: {"type": "match", "team_a": ["Pedro"], "team_b": ["Carlos"], "score_a": 5, "score_b": 3, "team_a_label": "A", "team_b_label": "B", "unknown_names": ["Tucu"], "question": "¿Quién es el Tucu? No lo tengo registrado."}

Mensaje de [Juan]: "Korea ayer estaba dormido, perdió tres pelotas seguidas"
Respuesta: {"type": "performance", "adjustments": [{"player": "Korea", "delta": -5, "reason": "perdió pelotas, jugó dormido"}]}

Mensaje de [Juan]: "hoy jugué como nunca, metí 3 goles"
Respuesta: {"type": "none"}
(autoelogio: Juan habla de sí mismo)

Mensaje: "qué golazo se comió el arquero de River anoche"
Respuesta: {"type": "none"}
(fútbol profesional, no del grupo)

Mensaje: "¿a qué hora jugamos mañana? ¿alguien lleva la pelota?"
Respuesta: {"type": "none"}

Jugadores registrados: <<PLAYERS>>
Aliases conocidos: <<ALIASES>>
Fecha actual: <<DATE>>

Mensaje de [<<AUTHOR>>]: <<MESSAGE>>"""


_MATCH_SIGNAL_WORDS = (
    "ganó", "gano", "ganamos", "ganaron", "perdió", "perdio", "perdimos", "perdieron",
    "goles", "goleada", "resultado", "empate", "empatamos", "empataron", " vs ", " vs.",
)


def _might_be_match(text_lower: str) -> bool:
    """Pre-filtro barato: sin señales de partido, no vale la pena llamar a la IA."""
    if re.search(r"\d+\s*(?:-|a)\s*\d+", text_lower):
        return True
    return any(kw in text_lower for kw in _MATCH_SIGNAL_WORDS)


def _mentions_registered_player(text_lower: str, players: list[dict], aliases: list[dict]) -> bool:
    """Pre-filtro barato: un comentario de rendimiento tiene que nombrar a alguien registrado."""
    names = [p["name"].lower() for p in players] + [a["alias"].lower() for a in aliases]
    return any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text_lower) for n in names if len(n) > 2)


async def analyze_group_message(text: str, author: str, author_telegram_id: int | None = None) -> dict | None:
    """
    Clasifica un mensaje del grupo con UNA llamada LLM (antes eran dos).
    Pre-filtros baratos descartan la mayoría de los mensajes sin llamar a la IA.

    Retorna:
    - {"kind": "match", ...} si registró un partido (equipos, scores, reply).
    - {"kind": "clarification", "unknown_names": [...], "question": str} si hay nombres sin resolver.
    - {"kind": "performance", "adjustments": [...], "reply": str} si ajustó ELOs por un comentario.
    - None si no hay nada relevante.
    """
    players = await get_all_players()
    aliases = await get_all_aliases()

    text_lower = text.lower()
    if not _might_be_match(text_lower) and not _mentions_registered_player(text_lower, players, aliases):
        return None

    player_names = [p["name"] for p in players]
    aliases_str = ", ".join(f"{a['alias']}→{a['canonical_name']}" for a in aliases) if aliases else "Ninguno"

    prompt = (
        CLASSIFY_PROMPT
        .replace("<<PLAYERS>>", ", ".join(player_names) if player_names else "Ninguno registrado aún")
        .replace("<<ALIASES>>", aliases_str)
        .replace("<<DATE>>", datetime.now().strftime("%Y-%m-%d"))
        .replace("<<AUTHOR>>", author)
        .replace("<<MESSAGE>>", text)
    )

    try:
        raw = await _post_llm(
            [{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.1,
            json_mode=True,
        )
        result = json.loads(_strip_code_fences(raw))
    except (json.JSONDecodeError, KeyError, httpx.HTTPError) as e:
        logger.warning(f"Error clasificando mensaje: {e}")
        return None

    msg_type = result.get("type")
    if msg_type == "match":
        return await _register_match(result)
    if msg_type == "performance":
        return await _apply_performance_adjustments(result, author, author_telegram_id)
    return None


async def _register_match(result: dict) -> dict | None:
    unknown = list(result.get("unknown_names") or [])

    team_a = result.get("team_a") or []
    team_b = result.get("team_b") or []
    if not team_a or not team_b:
        return None

    # Resolver cada nombre contra la DB (nombre canónico o alias).
    # En texto libre NO se auto-registran jugadores nuevos: eso creaba duplicados
    # ("Facu" y "Facundo" como jugadores distintos). Se pregunta; /resultado sí registra.
    resolved_a, resolved_b = [], []
    for name_list, resolved in ((team_a, resolved_a), (team_b, resolved_b)):
        for name in name_list:
            player = await get_player_by_name(name)
            if player:
                resolved.append(player["name"])
            elif name not in unknown:
                unknown.append(name)

    if unknown:
        question = result.get("question") or f"¿Quiénes son: {', '.join(unknown)}? No los tengo registrados."
        return {
            "kind": "clarification",
            "needs_clarification": True,
            "unknown_names": unknown,
            "question": question,
        }

    try:
        score_a = int(result["score_a"])
        score_b = int(result["score_b"])
    except (KeyError, TypeError, ValueError):
        return None

    match_id = await add_match(resolved_a, resolved_b, score_a, score_b)
    await update_elos_for_match(resolved_a, resolved_b, score_a, score_b)

    # Humor determinista desde la biblioteca: el parser corre a temperatura baja
    # y sus chistes salían repetidos; la biblioteca ya tiene frases curadas.
    reply = random.choice(FRASES_EMPATE if score_a == score_b else FRASES_VICTORIA + FRASES_DERROTA)

    return {
        "kind": "match",
        "match_id": match_id,
        "team_a": resolved_a,
        "team_b": resolved_b,
        "score_a": score_a,
        "score_b": score_b,
        "label_a": result.get("team_a_label") or "A",
        "label_b": result.get("team_b_label") or "B",
        "reply": reply,
    }


async def _apply_performance_adjustments(result: dict, author: str, author_telegram_id: int | None) -> dict | None:
    applied = []
    for adj in result.get("adjustments", []):
        try:
            delta = int(adj["delta"])
            target_name = adj["player"]
        except (KeyError, TypeError, ValueError):
            continue

        if delta == 0 or abs(delta) > MAX_SINGLE_DELTA:
            continue

        player = await get_player_by_name(target_name)
        if not player:
            continue

        # Nadie se ajusta el ELO a sí mismo (segunda línea de defensa tras el prompt)
        if author_telegram_id and player.get("telegram_id") == author_telegram_id:
            logger.info(f"Ajuste ignorado: {author} habla de sí mismo ({player['name']})")
            continue
        if player["name"].lower() == author.lower():
            continue

        used_today = await get_adjustment_abs_sum_today(player["id"])
        if used_today + abs(delta) > DAILY_ADJUSTMENT_CAP:
            logger.info(f"Cap diario alcanzado para {player['name']} ({used_today}/{DAILY_ADJUSTMENT_CAP}), ajuste ignorado")
            continue

        reason = str(adj.get("reason", ""))[:200]
        await update_player_elo(player["id"], round(player["elo"] + delta, 1), increment_matches=False)
        await add_elo_adjustment(player["id"], delta, reason, author)
        applied.append({"player": player["name"], "delta": delta, "reason": reason})
        logger.info(f"ELO ajustado: {player['name']} {delta:+d} ({reason}) por {author}")

    if not applied:
        return None

    first = applied[0]
    template = random.choice(HALAGOS if first["delta"] > 0 else CARGADAS_MAL)
    reply = template.format(nombre=first["player"])

    return {"kind": "performance", "adjustments": applied, "reply": reply}
