"""Command line entry point: `python -m stimulation --help`."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import replace

from .calibrate import format_checks, run_checks
from .data_loader import DEFAULT_DATA_PATH, load_players
from .derive import DEFAULT_STATS_PATH, apply_stats, format_provenance
from .engine import MatchEngine
from .models import FORMATIONS, PERSONALITY_KEYS, Team
from .monte_carlo import run_simulations
from .report import format_match, format_summary, summary_to_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stimulation",
        description="11 prime Messis vs 11 prime Ronaldos - Monte Carlo match simulator.",
    )
    parser.add_argument("-n", "--matches", type=int, default=2000, help="matches to simulate (default 2000)")
    parser.add_argument("--seed", type=int, default=42, help="random seed, same seed = same results")
    parser.add_argument("--knockout", action="store_true", help="no draws: extra time + penalty shootout")
    parser.add_argument("--single", action="store_true", help="play one match and show the goals")
    parser.add_argument("--home", default="messi", help="player id for team A (default messi)")
    parser.add_argument("--away", default="ronaldo", help="player id for team B (default ronaldo)")
    parser.add_argument("--home-formation", default="4-3-3", choices=sorted(FORMATIONS))
    parser.add_argument("--away-formation", default="4-3-3", choices=sorted(FORMATIONS))
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH), help="path to players JSON")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1, help="parallel processes")
    parser.add_argument("--neutral-personality", action="store_true",
                        help="set every personality trait to 50 (isolates pure ability from ego)")
    parser.add_argument("--stats", default=str(DEFAULT_STATS_PATH),
                        help="real stats used to derive ratings (messivsronaldo.app)")
    parser.add_argument("--estimates-only", action="store_true",
                        help="ignore real stats and use the hand-estimated ratings")
    parser.add_argument("--show-ratings", action="store_true",
                        help="print every rating and whether it comes from data or an estimate")
    parser.add_argument("--calibrate", action="store_true",
                        help="check the engine against real football benchmarks and exit")
    parser.add_argument("--json", action="store_true", help="print results as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    players = load_players(args.data)
    if not args.estimates_only:
        players, provenance = apply_stats(players, args.stats)
        if args.show_ratings:
            print(format_provenance(players, provenance))
            return 0

    if args.calibrate:
        print(format_checks(run_checks(players, matches=args.matches, seed=args.seed,
                                       workers=args.workers)))
        return 0
    for pid in (args.home, args.away):
        if pid not in players:
            print(f"Unknown player id {pid!r}. Available: {', '.join(players)}", file=sys.stderr)
            return 2

    if args.neutral_personality:
        players = {pid: replace(p, personality={k: 50 for k in PERSONALITY_KEYS})
                   for pid, p in players.items()}

    home = Team(f"Team {players[args.home].name.split()[-1]}", players[args.home], args.home_formation)
    away = Team(f"Team {players[args.away].name.split()[-1]}", players[args.away], args.away_formation)

    if args.single:
        result = MatchEngine(home, away, random.Random(args.seed), knockout=args.knockout).play()
        print(format_match(result))
        return 0

    started = time.perf_counter()
    summary = run_simulations(home, away, args.matches, seed=args.seed,
                              knockout=args.knockout, workers=args.workers)
    elapsed = time.perf_counter() - started
    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2))
    else:
        print(format_summary(summary))
        print(f"\n({elapsed:.1f}s, seed {args.seed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
