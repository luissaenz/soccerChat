import json
import re
from telegram import Update
from telegram.ext import ContextTypes
from bot.db import (
    add_player, get_all_players, get_player_by_name,
    add_match, get_recent_matches, add_comment,
    add_alias, get_aliases_for_player,
    link_telegram_to_player, get_player_by_telegram_id,
    delete_match
)
from bot.elo import update_elos_for_match, suggest_balanced_teams, recalculate_all_elos
from bot.ai import chat, analyze_comment, detect_match_result
from bot.analyst import format_player_report, format_full_leaderboard, analyst_chat


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Buenas, soy Mister, el DT virtual de este grupo de muertos.\n"
        "Comandos disponibles:\n"
        "/registrar <nombre> - Sumar jugador\n"
        "/jugadores - Ver ranking ELO\n"
        "/resultado <equipoA> <golA> - <equipoB> <golB> - Cargar resultado\n"
        "/equipos <nombre1, nombre2, ...> - Armar equipos\n"
        "/historial - Últimos partidos\n"
        "/alias <nombre> <apodo> - Registrar alias\n"
        "/stats <nombre> - Ficha estadística de un jugador 📊\n"
        "/tabla - Tabla de posiciones con stats completas 📈\n"
        "/analisis <pregunta> - Preguntale al Analista 🧠\n"
        "/recalcular - Recalcular todos los ELOs desde el historial 🔄\n"
        "/borrar_partido <id> - Eliminar un partido por ID 🗑️\n\n"
        "También pueden escribir los equipos y resultado en texto libre y yo los registro.\n"
        "Mencionenme o digan 'mister' y les contesto con la verdad que no quieren escuchar. 😏\n"
        "Digan 'analista' y responde El Analista con datos fríos. 📊"
    )


async def registrar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Dale, poné un nombre. /registrar <nombre>")
        return

    name = " ".join(context.args)
    existing = await get_player_by_name(name)
    if existing:
        await update.message.reply_text(f"'{name}' ya está registrado. ¿Querés otro? Inventá uno nuevo, crack.")
        return

    telegram_user = update.effective_user
    await add_player(
        name=name,
        telegram_username=telegram_user.username,
        telegram_id=telegram_user.id
    )
    await update.message.reply_text(f"✅ {name} registrado con ELO 1000. Veremos cuánto te dura esa ilusión.")


async def jugadores_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    players = await get_all_players()
    if not players:
        await update.message.reply_text("No hay jugadores registrados. ¿Juegan solos contra la pared?")
        return

    lines = []
    for i, p in enumerate(players, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        lines.append(f"{emoji} {i}. {p['name']} — ELO: {p['elo']:.0f} ({p['matches_played']} partidos)")

    await update.message.reply_text("🏆 *RANKING ELO*\n\n" + "\n".join(lines), parse_mode="Markdown")


async def resultado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Formato: /resultado NombreA,NombreB 3 - NombreC,NombreD 2
    """
    if not context.args:
        await update.message.reply_text(
            "Formato: /resultado JugadorA,JugadorB 3 - JugadorC,JugadorD 2\n"
            "Separar jugadores del mismo equipo con coma."
        )
        return

    text = " ".join(context.args)
    # Parse: "A,B 3 - C,D 2"
    match = re.match(r"^(.+?)\s+(\d+)\s*-\s*(.+?)\s+(\d+)$", text)
    if not match:
        await update.message.reply_text(
            "No entendí. Formato: /resultado JugA,JugB 3 - JugC,JugD 2"
        )
        return

    team_a_str, score_a_str, team_b_str, score_b_str = match.groups()
    team_a = [n.strip() for n in team_a_str.split(",")]
    team_b = [n.strip() for n in team_b_str.split(",")]
    score_a = int(score_a_str)
    score_b = int(score_b_str)

    # Auto-registrar jugadores que no existen
    for name in team_a + team_b:
        existing = await get_player_by_name(name)
        if not existing:
            await add_player(name=name)

    match_id = await add_match(team_a, team_b, score_a, score_b)
    await update_elos_for_match(team_a, team_b, score_a, score_b)

    result_emoji = "🏆" if score_a != score_b else "🤝"
    winner = ", ".join(team_a) if score_a > score_b else ", ".join(team_b) if score_b > score_a else "Empate"

    await update.message.reply_text(
        f"{result_emoji} Partido #{match_id} registrado!\n"
        f"[{', '.join(team_a)}] {score_a} - {score_b} [{', '.join(team_b)}]\n"
        f"{'Ganó: ' + winner if score_a != score_b else 'Empate'}\n\n"
        f"ELOs actualizados. Usá /jugadores para ver el ranking."
    )


async def equipos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Pasame los nombres separados por coma.\n"
            "Ejemplo: /equipos Juan, Pedro, Carlos, Luis, Martín, Diego"
        )
        return

    text = " ".join(context.args)
    names = [n.strip() for n in text.split(",")]

    if len(names) < 2:
        await update.message.reply_text("Necesito al menos 2 jugadores. ¿Van a jugar 1v1?")
        return

    team_a, team_b, diff = await suggest_balanced_teams(names)

    # Pedir a la IA un comentario sobre los equipos armados
    ai_prompt = (
        f"Armé estos equipos: {', '.join(team_a)} vs {', '.join(team_b)}. "
        f"La diferencia de ELO es {diff}. Hacé un comentario breve y sarcástico sobre los equipos."
    )
    ai_comment = await chat(ai_prompt, "Sistema")

    await update.message.reply_text(
        f"⚽ *EQUIPOS ARMADOS*\n\n"
        f"🔵 *Equipo A:* {', '.join(team_a)}\n"
        f"🔴 *Equipo B:* {', '.join(team_b)}\n"
        f"📊 Diferencia ELO: {diff}\n\n"
        f"🎙️ _{ai_comment}_",
        parse_mode="Markdown"
    )


async def historial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matches = await get_recent_matches(10)
    if not matches:
        await update.message.reply_text("No hay partidos registrados. ¿Recién se conocen?")
        return

    lines = []
    for m in matches:
        team_a_str = ", ".join(m["team_a"])
        team_b_str = ", ".join(m["team_b"])
        lines.append(f"📅 #{m['id']} {m['date'][:10]}: [{team_a_str}] {m['score_a']}-{m['score_b']} [{team_b_str}]")

    await update.message.reply_text("📋 *ÚLTIMOS PARTIDOS*\n\n" + "\n".join(lines), parse_mode="Markdown")


async def alias_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Formato: /alias NombreCanónico AliasoApodo
    Ejemplo: /alias Korea Koreano
    """
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Formato: /alias NombreRegistrado Apodo\n"
            "Ejemplo: /alias Korea Koreano\n"
            "Así cuando alguien diga 'Koreano' el sistema sabe que es Korea."
        )
        return

    canonical_name = context.args[0]
    alias_name = " ".join(context.args[1:])

    player = await get_player_by_name(canonical_name)
    if not player:
        await update.message.reply_text(
            f"No encontré a '{canonical_name}' registrado. Primero registralo con /registrar {canonical_name}"
        )
        return

    await add_alias(player["id"], alias_name)
    aliases = await get_aliases_for_player(player["id"])
    aliases_str = ", ".join(aliases)
    await update.message.reply_text(
        f"✅ Alias '{alias_name}' agregado para {player['name']}.\n"
        f"Aliases actuales: {aliases_str}"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ficha estadística de un jugador: /stats <nombre>"""
    if not context.args:
        await update.message.reply_text("Formato: /stats <nombre>\nEjemplo: /stats Korea")
        return

    name = " ".join(context.args)
    report = await format_player_report(name)
    await update.message.reply_text(report, parse_mode="Markdown")


async def tabla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tabla de posiciones con stats completas."""
    table = await format_full_leaderboard()
    await update.message.reply_text(table, parse_mode="Markdown")


async def borrar_partido_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un partido por ID: /borrar_partido <id>"""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Formato: /borrar_partido <id>\nUsá /historial para ver los IDs.")
        return
    match_id = int(context.args[0])
    await delete_match(match_id)
    await update.message.reply_text(
        f"🗑️ Partido #{match_id} eliminado.\n"
        f"Usá /recalcular para recalcular los ELOs desde el historial actualizado."
    )


async def recalcular_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recalcula todos los ELOs desde cero usando el historial de partidos en DB."""
    await update.message.reply_text("⏳ Recalculando ELOs desde el historial de partidos...")
    state = await recalculate_all_elos()
    recalculated = sorted(state.values(), key=lambda x: x["elo"], reverse=True)
    lines = [
        f"  {i}. {e['name']} — ELO: {e['elo']:.0f} ({e['matches']} partidos)"
        for i, e in enumerate(recalculated, 1)
    ]
    await update.message.reply_text(
        "✅ *ELOs recalculados desde cero* (historial completo)\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )


async def analisis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pregunta libre al Analista: /analisis <pregunta>"""
    if not context.args:
        await update.message.reply_text(
            "Formato: /analisis <pregunta>\n"
            "Ejemplo: /analisis ¿Quién es el jugador más consistente?\n"
            "Ejemplo: /analisis Compará a Korea con Esteban"
        )
        return

    question = " ".join(context.args)
    await update.message.reply_text("📊 Analizando datos...")
    response = await analyst_chat(question)
    await update.message.reply_text(response)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes que mencionan al bot o son respuestas a él."""
    if not update.message or not update.message.text:
        return

    message = update.message
    bot_username = context.bot.username
    text = message.text

    # Responder si mencionan al bot, le dicen "mister", o es reply a un mensaje del bot
    text_lower = text.lower()
    is_mention = bot_username and f"@{bot_username}" in text
    is_mister = "mister" in text_lower
    is_analyst = "analista" in text_lower
    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user and
        message.reply_to_message.from_user.id == context.bot.id
    )

    # Si mencionan al "analista", responde El Analista con datos
    if is_analyst:
        user_name = message.from_user.first_name or message.from_user.username or "Anónimo"
        clean_text = text_lower.replace("analista", "").strip()
        if not clean_text:
            clean_text = "Dame un resumen general del estado del grupo"
        response = await analyst_chat(clean_text)
        await message.reply_text(response)
        return

    # Detectar presentaciones: "soy Korea", "yo soy el Cachi", "me llamo Pancho", etc.
    presentation_match = re.match(
        r"(?:yo\s+)?(?:soy|me llamo|me dicen|soy el|soy la)\s+(.+)",
        text_lower.strip()
    )
    if presentation_match:
        claimed_name = presentation_match.group(1).strip().rstrip(".!,")
        # Buscar si ese nombre existe como jugador registrado
        player = await get_player_by_name(claimed_name)
        if player:
            telegram_id = message.from_user.id
            telegram_username = message.from_user.username
            # Verificar que no esté ya vinculado a otro
            existing_link = await get_player_by_telegram_id(telegram_id)
            if existing_link and existing_link["id"] == player["id"]:
                await message.reply_text(f"Ya te tengo registrado como {player['name']}. 👍")
            elif existing_link:
                await message.reply_text(
                    f"Ya estás vinculado como {existing_link['name']}. "
                    f"Si querés cambiar, pedile al admin."
                )
            else:
                await link_telegram_to_player(player["id"], telegram_id, telegram_username)
                await message.reply_text(
                    f"✅ Listo, {player['name']}! Te vinculé con tu cuenta de Telegram.\n"
                    f"Ahora te reconozco automáticamente y puedo darte stats personalizadas."
                )
            return

    if not is_mention and not is_mister and not is_reply_to_bot:
        # Guardar como comentario para contexto futuro
        user_name = message.from_user.first_name or message.from_user.username or "Anónimo"
        await add_comment(
            player_telegram_id=message.from_user.id,
            player_name=user_name,
            content=text
        )

        # Primero: detectar si es un resultado de partido
        match_result = await detect_match_result(text, user_name)
        if match_result:
            # Si la IA no pudo resolver algunos nombres, preguntar
            if match_result.get("needs_clarification"):
                unknown = match_result["unknown_names"]
                question = match_result["question"]
                await message.reply_text(
                    f"🤔 Detecté un partido pero no reconozco a: *{', '.join(unknown)}*\n\n"
                    f"{question}\n\n"
                    f"Podés:\n"
                    f"• Registrarlos con /registrar <nombre>\n"
                    f"• Agregar alias con /alias <nombre_registrado> <apodo>\n"
                    f"• Reenviar el mensaje con los nombres correctos",
                    parse_mode="Markdown"
                )
                return

            await message.reply_text(
                f"⚽ *Partido #{match_result['match_id']} registrado!*\n\n"
                f"🔵 *{match_result['label_a']}:* {', '.join(match_result['team_a'])}\n"
                f"🔴 *{match_result['label_b']}:* {', '.join(match_result['team_b'])}\n"
                f"📊 Resultado: {match_result['score_a']} - {match_result['score_b']}\n\n"
                f"🎙️ _{match_result['reply']}_\n\n"
                f"ELOs actualizados. Usá /jugadores para ver el ranking.",
                parse_mode="Markdown"
            )
            return

        # Si el mensaje parece un partido pero no se pudo parsear, avisar
        text_lower_check = text.lower()
        looks_like_match = (
            any(kw in text_lower_check for kw in ["equipo oscuro", "equipo claro", "team oscuro", "team claro"])
            and any(kw in text_lower_check for kw in ["ganó", "gano", "goles", "resultado"])
        )
        if looks_like_match:
            await message.reply_text(
                "🤔 Parece un resultado de partido pero no pude parsearlo bien.\n"
                "Probá con el formato:\n"
                "`/resultado JugA,JugB,JugC 8 - JugD,JugE,JugF 0`\n"
                "O volvé a escribir el mensaje mencionando a *Mister* para que lo intente de nuevo.",
                parse_mode="Markdown"
            )
            return

        # Segundo: analizar si el comentario habla de rendimiento y ajustar ELO
        result = await analyze_comment(text, user_name)
        if result:
            adj_lines = [f"  {a['player']} {a['delta']:+d} ({a['reason']})" for a in result["adjustments"]]
            await message.reply_text(
                f"🎙️ {result['reply']}\n\n📊 ELO actualizado:\n" + "\n".join(adj_lines)
            )
        return

    # Limpiar la mención del texto
    clean_text = text.replace(f"@{bot_username}", "").strip() if bot_username else text

    # Intentar identificar al usuario por su Telegram ID
    linked_player = await get_player_by_telegram_id(message.from_user.id)
    if linked_player:
        user_name = linked_player["name"]
    else:
        user_name = message.from_user.first_name or message.from_user.username or "Anónimo"

    # Guardar comentario
    await add_comment(
        player_telegram_id=message.from_user.id,
        player_name=user_name,
        content=clean_text
    )

    # Generar respuesta con IA (usa nombre real del jugador si está vinculado)
    response = await chat(clean_text, user_name)
    await message.reply_text(response)
