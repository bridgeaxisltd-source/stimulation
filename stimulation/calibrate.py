"""Checks the engine against real football numbers (data/benchmarks.json).

Two checks:
  1. Average vs average (trained keepers): must look like a normal top-flight match.
  2. 11 Messis vs average: must look at least like Guardiola's Barcelona in possession.
If either fails, the engine constants are wrong, whatever the Messi-Ronaldo result says.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import PlayerProfile, Team, baseline_profile
from .monte_carlo import SimulationSummary, run_simulations

DEFAULT_BENCHMARKS = Path(__file__).resolve().parent.parent / "data" / "benchmarks.json"


@dataclass
class Check:
    group: str
    name: str
    value: float
    low: float
    high: float
    evidence: str

    @property
    def ok(self) -> bool:
        return self.low <= self.value <= self.high


def _ratio(s: SimulationSummary, i: int, num: str, den: str) -> float:
    d = s.totals[i][den]
    return s.totals[i][num] / d if d else 0.0


def league_metrics(s: SimulationSummary) -> dict[str, float]:
    """Averaged over both (identical) sides."""
    def both(fn):
        return (fn(0) + fn(1)) / 2
    goals = both(lambda i: s.avg(i, "goals"))
    headers = sum(s.goal_types[i]["header"] for i in (0, 1))
    all_goals = sum(sum(s.goal_types[i].values()) for i in (0, 1)) or 1
    return {
        "goals_per_team": goals,
        "shots_per_team": both(lambda i: s.avg(i, "shots")),
        "shots_per_goal": both(lambda i: s.avg(i, "shots")) / goals if goals else 0.0,
        "crosses_per_team": both(lambda i: s.avg(i, "crosses_attempted")),
        "cross_completion": both(lambda i: _ratio(s, i, "crosses_completed", "crosses_attempted")),
        "headed_goal_share": headers / all_goals,
        "pass_accuracy": both(lambda i: _ratio(s, i, "passes_completed", "passes_attempted")),
        "possession_balance": s.avg_possession(0) / 100,
    }


def player_metrics(s: SimulationSummary) -> dict[str, float]:
    """Side 0 = 11 copies of the player, side 1 = average team."""
    goals = s.avg(0, "goals")
    return {
        "possession": s.avg_possession(0) / 100,
        "pass_accuracy": _ratio(s, 0, "passes_completed", "passes_attempted"),
        "dribble_success": _ratio(s, 0, "dribbles_completed", "dribbles_attempted"),
        "shots_per_goal": s.avg(0, "shots") / goals if goals else 0.0,
    }


def run_checks(players: dict[str, PlayerProfile], matches: int = 2000, seed: int = 7, workers: int = 1,
               benchmarks_path: str | Path = DEFAULT_BENCHMARKS) -> list[Check]:
    bench = json.loads(Path(benchmarks_path).read_text(encoding="utf-8"))
    avg = baseline_profile()
    a = Team("Average A", avg, trained_keeper=True)
    b = Team("Average B", avg, trained_keeper=True)
    league = league_metrics(run_simulations(a, b, matches, seed=seed, workers=workers))
    checks = [Check("average vs average", k, league[k], *v["range"], v["evidence"])
              for k, v in bench["league_average"].items()]

    for pid in ("messi", "ronaldo"):
        group = f"{pid}_vs_average"
        if group not in bench or pid not in players:
            continue
        s = run_simulations(Team(pid, players[pid]), Team("Average", avg, trained_keeper=True),
                            matches, seed=seed, workers=workers)
        values = player_metrics(s)
        checks += [Check(f"11 {players[pid].name.split()[-1]}s vs average", k, values[k], *v["range"], v["evidence"])
                   for k, v in bench[group].items()]
    return checks


def format_checks(checks: list[Check]) -> str:
    lines, group = [], None
    for c in checks:
        if c.group != group:
            group = c.group
            lines.append(f"\n{group.upper()}")
        mark = "PASS" if c.ok else "FAIL"
        fmt = "{:.1%}" if c.high <= 1.0 else "{:.2f}"
        lines.append(f"  [{mark}] {c.name:<20} {fmt.format(c.value):>8}   target "
                     f"{fmt.format(c.low)}-{fmt.format(c.high)}")
    passed = sum(c.ok for c in checks)
    lines.append(f"\n{passed}/{len(checks)} benchmarks inside their real-world range")
    return "\n".join(lines)
