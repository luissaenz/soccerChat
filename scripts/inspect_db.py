import asyncio
from dotenv import load_dotenv
load_dotenv()
from bot.db import get_all_players, get_all_matches

async def main():
    players = await get_all_players()
    print("=== JUGADORES ===")
    for p in players:
        print(f"  id={p['id']}  matches={p['matches_played']}  elo={p['elo']}  name={repr(p['name'])}")
    matches = await get_all_matches()
    print(f"\n=== PARTIDOS ({len(matches)}) ===")
    for m in matches:
        print(f"  #{m['id']}  score={m['score_a']}-{m['score_b']}  A={m['team_a']}  B={m['team_b']}")

asyncio.run(main())
