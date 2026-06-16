from bot.db import get_player_by_name, update_player_elo, get_all_players

K_FACTOR = 32


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def calculate_new_elo(rating: float, expected: float, actual: float) -> float:
    return rating + K_FACTOR * (actual - expected)


async def update_elos_for_match(team_a_names: list[str], team_b_names: list[str], score_a: int, score_b: int):
    """
    Actualiza el ELO de todos los jugadores de un partido.
    actual: 1.0 = victoria, 0.5 = empate, 0.0 = derrota
    Se usa el promedio de ELO del equipo contrario como rating rival.
    """
    players = await get_all_players()
    player_map = {p["name"].lower(): p for p in players}

    team_a_players = [player_map[n.lower()] for n in team_a_names if n.lower() in player_map]
    team_b_players = [player_map[n.lower()] for n in team_b_names if n.lower() in player_map]

    if not team_a_players or not team_b_players:
        return

    avg_elo_a = sum(p["elo"] for p in team_a_players) / len(team_a_players)
    avg_elo_b = sum(p["elo"] for p in team_b_players) / len(team_b_players)

    if score_a > score_b:
        actual_a, actual_b = 1.0, 0.0
    elif score_a < score_b:
        actual_a, actual_b = 0.0, 1.0
    else:
        actual_a, actual_b = 0.5, 0.5

    for p in team_a_players:
        exp = expected_score(p["elo"], avg_elo_b)
        new_elo = calculate_new_elo(p["elo"], exp, actual_a)
        await update_player_elo(p["id"], round(new_elo, 1))

    for p in team_b_players:
        exp = expected_score(p["elo"], avg_elo_a)
        new_elo = calculate_new_elo(p["elo"], exp, actual_b)
        await update_player_elo(p["id"], round(new_elo, 1))


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
