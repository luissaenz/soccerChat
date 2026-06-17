import math
from bot.db import get_player_by_name, update_player_elo, get_all_players, reset_player_elos, get_all_matches, set_player_matches_played, bulk_update_player_elos

K_FACTOR = 32


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def goal_diff_multiplier(goal_diff: int) -> float:
    """
    Multiplicador suave basado en diferencia de goles.
    1 gol → 1.0x, 2 goles → 1.1x, 3 → 1.2x ... 8 → 1.5x
    Usa log para que no se dispare con goleadas absurdas.
    """
    if goal_diff <= 1:
        return 1.0
    return 1.0 + math.log2(goal_diff) * 0.2


def calculate_new_elo(rating: float, expected: float, actual: float, gd_mult: float = 1.0) -> float:
    return rating + K_FACTOR * gd_mult * (actual - expected)


async def update_elos_for_match(team_a_names: list[str], team_b_names: list[str], score_a: int, score_b: int):
    """
    Actualiza el ELO de todos los jugadores de un partido.
    actual: 1.0 = victoria, 0.5 = empate, 0.0 = derrota
    Se usa el promedio de ELO del equipo contrario como rating rival.
    La diferencia de goles aplica un multiplicador suave al cambio de ELO.
    """
    players = await get_all_players()
    player_map = {p["name"].lower(): p for p in players}

    team_a_players = [player_map[n.lower()] for n in team_a_names if n.lower() in player_map]
    team_b_players = [player_map[n.lower()] for n in team_b_names if n.lower() in player_map]

    if not team_a_players or not team_b_players:
        return

    avg_elo_a = sum(p["elo"] for p in team_a_players) / len(team_a_players)
    avg_elo_b = sum(p["elo"] for p in team_b_players) / len(team_b_players)

    goal_diff = abs(score_a - score_b)
    gd_mult = goal_diff_multiplier(goal_diff)

    if score_a > score_b:
        actual_a, actual_b = 1.0, 0.0
    elif score_a < score_b:
        actual_a, actual_b = 0.0, 1.0
    else:
        actual_a, actual_b = 0.5, 0.5

    for p in team_a_players:
        exp = expected_score(p["elo"], avg_elo_b)
        new_elo = calculate_new_elo(p["elo"], exp, actual_a, gd_mult)
        await update_player_elo(p["id"], round(new_elo, 1))

    for p in team_b_players:
        exp = expected_score(p["elo"], avg_elo_a)
        new_elo = calculate_new_elo(p["elo"], exp, actual_b, gd_mult)
        await update_player_elo(p["id"], round(new_elo, 1))


async def recalculate_all_elos() -> dict[str, dict]:
    """
    Recalcula TODOS los ELOs desde cero usando el historial de partidos en la DB.
    Proceso determinista: parte desde 1000 para todos y aplica los partidos en orden cronológico.
    Retorna un dict {nombre_lower: {"elo": float, "matches": int}} con el estado final.
    """
    await reset_player_elos()

    all_matches = await get_all_matches()
    # Ordenar cronológicamente (más viejo primero)
    all_matches = sorted(all_matches, key=lambda m: m["date"])

    players = await get_all_players()
    # Estado en memoria: {nombre_lower: {"id": int, "name": str, "elo": float, "matches": int}}
    state: dict[str, dict] = {
        p["name"].lower(): {"id": p["id"], "name": p["name"], "elo": 1000.0, "matches": 0}
        for p in players
    }

    for match in all_matches:
        team_a_names = [n for n in match["team_a"] if n.lower() in state]
        team_b_names = [n for n in match["team_b"] if n.lower() in state]

        if not team_a_names or not team_b_names:
            continue

        avg_elo_a = sum(state[n.lower()]["elo"] for n in team_a_names) / len(team_a_names)
        avg_elo_b = sum(state[n.lower()]["elo"] for n in team_b_names) / len(team_b_names)

        score_a = match["score_a"]
        score_b = match["score_b"]
        goal_diff = abs(score_a - score_b)
        gd_mult = goal_diff_multiplier(goal_diff)

        if score_a > score_b:
            actual_a, actual_b = 1.0, 0.0
        elif score_a < score_b:
            actual_a, actual_b = 0.0, 1.0
        else:
            actual_a, actual_b = 0.5, 0.5

        for name in team_a_names:
            key = name.lower()
            exp = expected_score(state[key]["elo"], avg_elo_b)
            state[key]["elo"] = round(state[key]["elo"] + K_FACTOR * gd_mult * (actual_a - exp), 1)
            state[key]["matches"] += 1

        for name in team_b_names:
            key = name.lower()
            exp = expected_score(state[key]["elo"], avg_elo_a)
            state[key]["elo"] = round(state[key]["elo"] + K_FACTOR * gd_mult * (actual_b - exp), 1)
            state[key]["matches"] += 1

    # Persistir todos los resultados en una sola transacción batch
    await bulk_update_player_elos(list(state.values()))

    return state


async def suggest_balanced_teams(player_names: list[str]) -> tuple[list[str], list[str], float]:
    """
    Dado una lista de nombres, devuelve la división más equilibrada en 2 equipos.
    Retorna (team_a, team_b, diferencia_elo).
    """
    from itertools import combinations

    players = await get_all_players()
    player_map = {p["name"].lower(): p for p in players}

    available = [n for n in player_names if n.lower() in player_map]
    if len(available) < 2:
        half = len(player_names) // 2
        return player_names[:half], player_names[half:], 0.0

    n = len(available)
    half = n // 2
    best_diff = float("inf")
    best_a = []
    best_b = []

    for combo in combinations(range(n), half):
        team_a = [available[i] for i in combo]
        team_b = [available[i] for i in range(n) if i not in combo]

        elo_a = sum(player_map[p.lower()]["elo"] for p in team_a)
        elo_b = sum(player_map[p.lower()]["elo"] for p in team_b)
        diff = abs(elo_a - elo_b)

        if diff < best_diff:
            best_diff = diff
            best_a = team_a
            best_b = team_b

    return best_a, best_b, round(best_diff, 1)
