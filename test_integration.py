"""
Integration tests against the real production DB (Turso) and real ELO logic.
Uses TEST_ prefixed player names so production data is never touched.
Cleans up all created records at the end regardless of failures.

Run with:
    python test_integration.py
"""

import asyncio
import math
import sys
import os
from dotenv import load_dotenv

load_dotenv()

from bot.db import (
    add_player, get_player_by_name, get_all_players,
    add_match, get_all_matches, get_recent_matches,
    delete_match, reset_player_elos, set_player_matches_played,
    update_player_elo, bulk_update_player_elos, _execute,
)
from bot.elo import (
    expected_score, goal_diff_multiplier, calculate_new_elo,
    update_elos_for_match, recalculate_all_elos,
)

# ---------------------------------------------------------------------------
# Test player names — all prefixed with TEST_ to isolate from real data
# ---------------------------------------------------------------------------
TEST_TEAM_A = ["TEST_Luis", "TEST_Esteban", "TEST_Christian", "TEST_Pancho", "TEST_Daniel", "TEST_Gonzalo", "TEST_Facundo"]
TEST_TEAM_B = ["TEST_Roberto", "TEST_Cachi", "TEST_Korea", "TEST_Juan", "TEST_EstebanCM", "TEST_Jose", "TEST_DiegoSosa"]
ALL_TEST_PLAYERS = TEST_TEAM_A + TEST_TEAM_B

PASS = "✅"
FAIL = "❌"
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = ""):
    icon = PASS if condition else FAIL
    results.append((name, condition, detail))
    status = f"{icon} {name}"
    if detail:
        status += f"  ({detail})"
    print(status)
    return condition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def cleanup(match_ids: list[int]):
    """Remove all test players and test matches from DB."""
    for mid in match_ids:
        try:
            await delete_match(mid)
        except Exception:
            pass
    for name in ALL_TEST_PLAYERS:
        try:
            await _execute("DELETE FROM players WHERE name = ?", [name])
        except Exception:
            pass


async def register_test_players():
    ids = {}
    for name in ALL_TEST_PLAYERS:
        existing = await get_player_by_name(name)
        if existing:
            ids[name] = existing["id"]
        else:
            pid = await add_player(name=name)
            ids[name] = pid
    return ids


def compute_expected_elos(
    team_a: list[str], team_b: list[str],
    score_a: int, score_b: int,
    starting_elo: float = 1000.0,
) -> dict[str, float]:
    """
    Pure-Python reference ELO calculation matching elo.py logic exactly.
    All players start at starting_elo.
    Returns {name_lower: new_elo}.
    """
    state = {n.lower(): starting_elo for n in team_a + team_b}
    avg_a = sum(state[n.lower()] for n in team_a) / len(team_a)
    avg_b = sum(state[n.lower()] for n in team_b) / len(team_b)
    gd = abs(score_a - score_b)
    mult = goal_diff_multiplier(gd)
    if score_a > score_b:
        act_a, act_b = 1.0, 0.0
    elif score_a < score_b:
        act_a, act_b = 0.0, 1.0
    else:
        act_a, act_b = 0.5, 0.5
    result = {}
    for name in team_a:
        exp = expected_score(state[name.lower()], avg_b)
        result[name.lower()] = round(state[name.lower()] + 32 * mult * (act_a - exp), 1)
    for name in team_b:
        exp = expected_score(state[name.lower()], avg_a)
        result[name.lower()] = round(state[name.lower()] + 32 * mult * (act_b - exp), 1)
    return result


# ---------------------------------------------------------------------------
# Real match data (prefixed with TEST_ to isolate)
# ---------------------------------------------------------------------------

REAL_MATCH_1 = {
    "team_a": ["TEST_Esteban", "TEST_Gonzalo", "TEST_Marcos", "TEST_Pancho", "TEST_EstebanCM", "TEST_DiegoSosa", "TEST_Juan"],
    "team_b": ["TEST_Daniel", "TEST_Roberto", "TEST_Korea", "TEST_Jose", "TEST_Christian", "TEST_Cachi", "TEST_Facu"],
    "score_a": 8, "score_b": 0,   # equipo oscuro (a) gana por 8
}
REAL_MATCH_2 = {
    "team_a": ["TEST_Esteban", "TEST_Roberto", "TEST_Gonzalo", "TEST_Cordobes", "TEST_Daniel", "TEST_Cachi", "TEST_Marcos"],
    "team_b": ["TEST_Luis", "TEST_EstebanCM", "TEST_Korea", "TEST_Jose", "TEST_Christian", "TEST_DiegoSosa", "TEST_Pancho"],
    "score_a": 1, "score_b": 0,   # equipo claro (a) gana
}
REAL_MATCH_3 = {
    "team_a": ["TEST_Luis", "TEST_Esteban", "TEST_Christian", "TEST_Pancho", "TEST_Daniel", "TEST_Gonzalo", "TEST_Facundo"],
    "team_b": ["TEST_Roberto", "TEST_Cachi", "TEST_Korea", "TEST_Juan", "TEST_EstebanCM", "TEST_Jose", "TEST_DiegoSosa"],
    "score_a": 7, "score_b": 0,   # equipo claro (a) gana por 7
}

REAL_MATCHES = [REAL_MATCH_1, REAL_MATCH_2, REAL_MATCH_3]

# All unique player names across the 3 real matches
REAL_ALL_PLAYERS = sorted({
    n
    for m in REAL_MATCHES
    for n in m["team_a"] + m["team_b"]
})

# Expected matches_played per player derived from the data above
def _count_matches_played() -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in REAL_MATCHES:
        for n in m["team_a"] + m["team_b"]:
            counts[n] = counts.get(n, 0) + 1
    return counts

REAL_EXPECTED_MATCHES = _count_matches_played()


def simulate_elos_sequential(matches: list[dict]) -> dict[str, float]:
    """
    Pure-Python sequential ELO simulation over multiple matches.
    Mirrors recalculate_all_elos logic exactly.
    Returns {name_lower: final_elo}.
    """
    all_names = {n for m in matches for n in m["team_a"] + m["team_b"]}
    state = {n.lower(): 1000.0 for n in all_names}

    for m in matches:
        team_a = m["team_a"]
        team_b = m["team_b"]
        score_a = m["score_a"]
        score_b = m["score_b"]

        avg_a = sum(state[n.lower()] for n in team_a) / len(team_a)
        avg_b = sum(state[n.lower()] for n in team_b) / len(team_b)
        gd = abs(score_a - score_b)
        mult = goal_diff_multiplier(gd)

        if score_a > score_b:
            act_a, act_b = 1.0, 0.0
        elif score_a < score_b:
            act_a, act_b = 0.0, 1.0
        else:
            act_a, act_b = 0.5, 0.5

        new_state = dict(state)
        for n in team_a:
            key = n.lower()
            exp = expected_score(state[key], avg_b)
            new_state[key] = round(state[key] + 32 * mult * (act_a - exp), 1)
        for n in team_b:
            key = n.lower()
            exp = expected_score(state[key], avg_a)
            new_state[key] = round(state[key] + 32 * mult * (act_b - exp), 1)
        state = new_state

    return state


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

async def test_unit_elo_math():
    print("\n--- Unit: ELO math ---")

    # Equal teams, winner gets +16 (K/2), loser -16
    exp = expected_score(1000.0, 1000.0)
    check("expected_score equal teams = 0.5", abs(exp - 0.5) < 1e-9, f"{exp:.6f}")

    new = calculate_new_elo(1000.0, 0.5, 1.0)
    check("winner gains 16 ELO (no gd mult)", abs(new - 1016.0) < 1e-9, f"{new:.1f}")

    new = calculate_new_elo(1000.0, 0.5, 0.0)
    check("loser loses 16 ELO (no gd mult)", abs(new - 984.0) < 1e-9, f"{new:.1f}")

    mult = goal_diff_multiplier(1)
    check("gd_mult(1) = 1.0", mult == 1.0, str(mult))

    mult7 = goal_diff_multiplier(7)
    expected_mult = round(1.0 + math.log2(7) * 0.2, 10)
    check("gd_mult(7) matches formula", abs(mult7 - expected_mult) < 1e-9, f"{mult7:.4f}")


async def test_add_match_and_elo(match_ids: list[int]):
    print("\n--- Integration: add match + ELO update ---")

    # Match 1: TEST_TEAM_A wins 7-0 over TEST_TEAM_B
    score_a, score_b = 7, 0
    mid = await add_match(TEST_TEAM_A, TEST_TEAM_B, score_a, score_b)
    match_ids.append(mid)
    check("add_match returns valid ID", isinstance(mid, int) and mid > 0, str(mid))

    await update_elos_for_match(TEST_TEAM_A, TEST_TEAM_B, score_a, score_b)

    # Verify ELOs in DB match reference calculation
    expected = compute_expected_elos(TEST_TEAM_A, TEST_TEAM_B, score_a, score_b)
    all_ok = True
    for name in ALL_TEST_PLAYERS:
        player = await get_player_by_name(name)
        db_elo = player["elo"]
        ref_elo = expected[name.lower()]
        ok = abs(db_elo - ref_elo) < 0.2
        if not ok:
            all_ok = False
            print(f"  {FAIL} {name}: DB={db_elo} expected={ref_elo}")
    check("ELOs match reference calculation after match 1", all_ok)

    # winners should have ELO > 1000, losers < 1000
    winners_up = True
    for n in TEST_TEAM_A:
        p = await get_player_by_name(n)
        if p["elo"] <= 1000:
            winners_up = False
    losers_down = True
    for n in TEST_TEAM_B:
        p = await get_player_by_name(n)
        if p["elo"] >= 1000:
            losers_down = False
    check("All winners have ELO > 1000", winners_up)
    check("All losers have ELO < 1000", losers_down)

    # matches_played should be 1 for all
    correct_count = True
    for n in ALL_TEST_PLAYERS:
        p = await get_player_by_name(n)
        if p["matches_played"] != 1:
            correct_count = False
    check("matches_played = 1 for all 14 players after match 1", correct_count)

    return mid


async def test_historial(match_ids: list[int]):
    print("\n--- Integration: historial ---")

    recent = await get_recent_matches(20)
    test_matches = [m for m in recent if m["id"] in match_ids]
    check(
        f"Historial contains all {len(match_ids)} test match(es)",
        len(test_matches) == len(match_ids),
        f"found {len(test_matches)}",
    )

    if test_matches:
        m = next(m for m in test_matches if m["id"] == match_ids[0])
        check(
            "Match team_a stored correctly",
            set(m["team_a"]) == set(TEST_TEAM_A),
            str(m["team_a"]),
        )
        check(
            "Match team_b stored correctly",
            set(m["team_b"]) == set(TEST_TEAM_B),
            str(m["team_b"]),
        )
        check("Score stored correctly (7-0)", m["score_a"] == 7 and m["score_b"] == 0)


async def test_recalculate(match_ids: list[int]):
    print("\n--- Integration: recalculate_all_elos ---")

    # Add a second match (TEST_TEAM_B wins 8-0) — roles swapped
    score_a2, score_b2 = 0, 8
    mid2 = await add_match(TEST_TEAM_A, TEST_TEAM_B, score_a2, score_b2)
    match_ids.append(mid2)
    await update_elos_for_match(TEST_TEAM_A, TEST_TEAM_B, score_a2, score_b2)

    # Snapshot ELOs before recalculate
    before = {p["name"]: p["elo"] for p in await get_all_players() if p["name"] in ALL_TEST_PLAYERS}

    # Run recalculate
    state = await recalculate_all_elos()

    after = {p["name"]: p["elo"] for p in await get_all_players() if p["name"] in ALL_TEST_PLAYERS}

    # recalculate should produce deterministic results equal to before
    # (because it replays the same 2 matches from scratch)
    diffs = {n: abs(before[n] - after[n]) for n in before if n in after}
    max_diff = max(diffs.values()) if diffs else 0
    check(
        "recalculate_all_elos is deterministic (matches incremental result)",
        max_diff < 0.2,
        f"max diff={max_diff:.2f}",
    )

    # matches_played should be 2 for all players who played both matches
    correct_counts = all(
        state[n.lower()]["matches"] == 2
        for n in ALL_TEST_PLAYERS
        if n.lower() in state
    )
    check("matches_played = 2 for all test players after 2 matches", correct_counts)

    # Running recalculate again should give the same result (idempotent)
    state2 = await recalculate_all_elos()
    diffs2 = {n: abs(state[n]["elo"] - state2[n]["elo"]) for n in state if n in state2}
    max_diff2 = max(diffs2.values()) if diffs2 else 0
    check(
        "recalculate_all_elos is idempotent (same result on second run)",
        max_diff2 < 0.2,
        f"max diff={max_diff2:.2f}",
    )


async def test_delete_match(match_ids: list[int]):
    print("\n--- Integration: delete_match ---")

    mid = match_ids[-1]
    await delete_match(mid)
    recent = await get_recent_matches(50)
    found = any(m["id"] == mid for m in recent)
    check(f"Deleted match #{mid} not in historial", not found)
    # Remove from tracking so cleanup doesn't try to delete again
    match_ids.remove(mid)


async def test_real_matches(real_match_ids: list[int]):
    print("\n--- Real match data: 3 partidos reales ---")

    # Register real test players
    for name in REAL_ALL_PLAYERS:
        existing = await get_player_by_name(name)
        if not existing:
            await add_player(name=name)

    registered = [p for p in await get_all_players() if p["name"] in REAL_ALL_PLAYERS]
    check(
        f"All {len(REAL_ALL_PLAYERS)} real-match players registered",
        len(registered) == len(REAL_ALL_PLAYERS),
        f"found {len(registered)}",
    )

    # Reset real-match players to ELO 1000 / 0 matches so this suite is isolated
    # from whatever the previous test suites left in the DB
    for name in REAL_ALL_PLAYERS:
        p = await get_player_by_name(name)
        if p:
            await update_player_elo(p["id"], 1000.0, increment_matches=False)
            await set_player_matches_played(p["id"], 0)

    # Insert and apply ELOs for each match in order
    for i, m in enumerate(REAL_MATCHES, 1):
        mid = await add_match(m["team_a"], m["team_b"], m["score_a"], m["score_b"])
        real_match_ids.append(mid)
        await update_elos_for_match(m["team_a"], m["team_b"], m["score_a"], m["score_b"])
        check(f"Partido {i} registrado (ID #{mid})", isinstance(mid, int) and mid > 0, str(mid))

    # Compute expected final ELOs via pure-Python simulation (all start at 1000)
    expected_elos = simulate_elos_sequential(REAL_MATCHES)

    # Verify DB ELOs match simulation
    elo_ok = True
    print("\n  ELO final por jugador (simulado → DB):")
    for name in sorted(REAL_ALL_PLAYERS):
        p = await get_player_by_name(name)
        db_elo = p["elo"]
        ref_elo = expected_elos.get(name.lower(), None)
        if ref_elo is None:
            continue
        diff = abs(db_elo - ref_elo)
        ok = diff < 0.2
        if not ok:
            elo_ok = False
        icon = PASS if ok else FAIL
        print(f"  {icon} {name.replace('TEST_',''):15s}  sim={ref_elo:.1f}  db={db_elo:.1f}")
    check("ELOs en DB coinciden con simulación secuencial", elo_ok)

    # Verify matches_played per player
    mp_ok = True
    mp_errors = []
    for name in REAL_ALL_PLAYERS:
        p = await get_player_by_name(name)
        expected_mp = REAL_EXPECTED_MATCHES.get(name, 0)
        if p["matches_played"] != expected_mp:
            mp_ok = False
            mp_errors.append(f"{name.replace('TEST_','')}: got {p['matches_played']} expected {expected_mp}")
    check(
        "matches_played correcto para cada jugador",
        mp_ok,
        "; ".join(mp_errors) if mp_errors else "",
    )

    # Verify all 3 matches appear in historial
    recent = await get_recent_matches(50)
    found_ids = {m["id"] for m in recent}
    all_in_historial = all(mid in found_ids for mid in real_match_ids)
    check(
        "Los 3 partidos aparecen en /historial",
        all_in_historial,
        f"expected {real_match_ids}, found {[mid for mid in real_match_ids if mid in found_ids]}",
    )

    # Verify recalculate_all_elos is idempotent with real data:
    # running it twice must produce the exact same ELOs (deterministic replay).
    state_r1 = await recalculate_all_elos()
    state_r2 = await recalculate_all_elos()
    recalc_ok = True
    recalc_errors = []
    for key in state_r1:
        if key not in state_r2:
            continue
        diff = abs(state_r1[key]["elo"] - state_r2[key]["elo"])
        if diff >= 0.2:
            recalc_ok = False
            recalc_errors.append(f"{key}: r1={state_r1[key]['elo']:.1f} r2={state_r2[key]['elo']:.1f}")
    check(
        "recalculate_all_elos es idempotente con datos reales (2 corridas = mismo resultado)",
        recalc_ok,
        "; ".join(recalc_errors) if recalc_errors else f"{len(state_r1)} jugadores verificados",
    )

    # Also verify that after recalculate, matches_played for real-only players
    # (Cordobes, Facu, Marcos) equals their expected count (they only appear in real matches)
    real_only = ["TEST_Cordobes", "TEST_Facu", "TEST_Marcos"]
    mp_recalc_ok = True
    mp_recalc_errors = []
    for name in real_only:
        key = name.lower()
        if key not in state_r2:
            continue
        expected_mp = REAL_EXPECTED_MATCHES.get(name, 0)
        got = state_r2[key]["matches"]
        if got != expected_mp:
            mp_recalc_ok = False
            mp_recalc_errors.append(f"{name.replace('TEST_','')}: got {got} expected {expected_mp}")
    check(
        "recalculate_all_elos: matches_played correcto para jugadores exclusivos de los 3 partidos",
        mp_recalc_ok,
        "; ".join(mp_recalc_errors) if mp_recalc_errors else "",
    )


async def cleanup_real(real_match_ids: list[int]):
    for mid in real_match_ids:
        try:
            await delete_match(mid)
        except Exception:
            pass
    for name in REAL_ALL_PLAYERS:
        try:
            await _execute("DELETE FROM players WHERE name = ?", [name])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("SoccerChat Integration Tests")
    print("DB:", os.getenv("TURSO_DATABASE_URL", "(hardcoded in db.py)"))
    print("=" * 60)

    match_ids: list[int] = []
    real_match_ids: list[int] = []

    try:
        # Setup
        print("\n--- Setup: registering test players ---")
        await register_test_players()
        players = await get_all_players()
        test_registered = [p for p in players if p["name"] in ALL_TEST_PLAYERS]
        check(
            f"All {len(ALL_TEST_PLAYERS)} test players registered",
            len(test_registered) == len(ALL_TEST_PLAYERS),
            f"found {len(test_registered)}",
        )

        # Run tests
        await test_unit_elo_math()
        await test_add_match_and_elo(match_ids)
        await test_historial(match_ids)
        await test_recalculate(match_ids)
        await test_delete_match(match_ids)
        await test_real_matches(real_match_ids)

    finally:
        print("\n--- Cleanup: removing test data ---")
        await cleanup(match_ids)
        await cleanup_real(real_match_ids)
        # Verify cleanup
        all_test_names = set(ALL_TEST_PLAYERS) | set(REAL_ALL_PLAYERS)
        remaining = [p for p in await get_all_players() if p["name"] in all_test_names]
        check("All test players removed from DB", len(remaining) == 0, f"{len(remaining)} remaining")

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"Results: {passed} passed, {failed} failed out of {len(results)} checks")
    if failed:
        print("\nFailed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"  {FAIL} {name}  {detail}")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
