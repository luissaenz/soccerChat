import json
import re
from telegram import Update
from telegram.ext import ContextTypes
from bot.db import (
    add_player, get_all_players, get_player_by_name,
    add_match, get_recent_matches, add_comment
)
from bot.elo import update_elos_for_match, suggest_balanced_teams
from bot.ai import chat, analyze_comment


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Buenas, soy el DT virtual de este grupo de muertos.\n"
        "Comandos disponibles:\n"
        "/registrar <nombre> - Sumar jugador\n"
        "/jugadores - Ver ranking ELO\n"
        "/resultado <equipoA> <golA> - <equipoB> <golB> - Cargar resultado\n"
        "/equipos <nombre1, nombre2, ...> - Armar equipos\n"
        "/historial - Últimos partidos\n\n"
        "También pueden hablarme mencionándome y les contesto con la verdad que no quieren escuchar. 😏"
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
        lines.append(f"📅 {m['date'][:10]}: [{team_a_str}] {m['score_a']}-{m['score_b']} [{team_b_str}]")

    await update.message.reply_text("📋 *ÚLTIMOS PARTIDOS*\n\n" + "\n".join(lines), parse_mode="Markdown")


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
    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user and
        message.reply_to_message.from_user.id == context.bot.id
    )

    if not is_mention and not is_mister and not is_reply_to_bot:
        # Guardar como comentario para contexto futuro
        user_name = message.from_user.first_name or message.from_user.username or "Anónimo"
        await add_comment(
            player_telegram_id=message.from_user.id,
            player_name=user_name,
            content=text
        )

        # Analizar si el comentario habla de rendimiento y ajustar ELO
        result = await analyze_comment(text, user_name)
        if result:
            adj_lines = [f"  {a['player']} {a['delta']:+d} ({a['reason']})" for a in result["adjustments"]]
            await message.reply_text(
                f"🎙️ {result['reply']}\n\n📊 ELO actualizado:\n" + "\n".join(adj_lines)
            )
        return

    # Limpiar la mención del texto
    clean_text = text.replace(f"@{bot_username}", "").strip() if bot_username else text
    user_name = message.from_user.first_name or message.from_user.username or "Anónimo"

    # Guardar comentario
    await add_comment(
        player_telegram_id=message.from_user.id,
        player_name=user_name,
        content=clean_text
    )

    # Generar respuesta con IA
    response = await chat(clean_text, user_name)
    await message.reply_text(response)
