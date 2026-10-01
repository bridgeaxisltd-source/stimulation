"""Runs many matches and aggregates the results."""

from __future__ import annotations

import math
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

from .engine import MatchEngine, MatchResult
from .models import Team

STAT_FIELDS = (
    "goals", "shots", "shots_on_target", "xg", "passes_attempted", "passes_completed",
    "dribbles_attempted", "dribbles_completed", "aerials_won", "fouls_won", "corners", "counters",
)


@dataclass
class SimulationSummary:
    names: tuple[str, str]
    matches: int
    knockout: bool
    wins: list[int] = field(default_factory=lambda: [0, 0])
    draws: int = 0
    shootouts: int = 0
    totals: list[dict[str, float]] = field(default_factory=lambda: [Counter(), Counter()])
    possession_pct_sum: list[float] = field(default_factory=lambda: [0.0, 0.0])
    goal_types: list[Counter] = field(default_factory=lambda: [Counter(), Counter()])
    scorelines: Counter = field(default_factory=Counter)
    biggest_win: list[tuple[int, int] | None] = field(default_factory=lambda: [None, None])

    def add(self, result: MatchResult, home_side: int) -> None:
        """`home_side` maps engine slot 0 back to summary slot (we alternate kickoffs)."""
        order = (0, 1) if home_side == 0 else (1, 0)  # order[summary_idx] = engine_idx
        goals = (result.goals[order[0]], result.goals[order[1]])
        winner = result.winner
        if winner is None:
            self.draws += 1
        else:
            self.wins[order.index(winner)] += 1
        if result.shootout:
            self.shootouts += 1
        self.scorelines[goals] += 1
        for i in (0, 1):
            st = result.stats[order[i]]
            for f in STAT_FIELDS:
                self.totals[i][f] += getattr(st, f)
            self.possession_pct_sum[i] += result.possession_pct(order[i])
            self.goal_types[i].update(st.goal_types)
            margin = goals[i] - goals[1 - i]
            best = self.biggest_win[i]
            if margin > 0 and (best is None or margin > best[0] - best[1]):
                self.biggest_win[i] = (goals[i], goals[1 - i])

    def merge(self, other: SimulationSummary) -> None:
        self.matches += other.matches
        self.draws += other.draws
        self.shootouts += other.shootouts
        self.scorelines.update(other.scorelines)
        for i in (0, 1):
            self.wins[i] += other.wins[i]
            self.totals[i].update(other.totals[i])
            self.possession_pct_sum[i] += other.possession_pct_sum[i]
            self.goal_types[i].update(other.goal_types[i])
            a, b = self.biggest_win[i], other.biggest_win[i]
            if b and (a is None or b[0] - b[1] > a[0] - a[1]):
                self.biggest_win[i] = b

    # ------------------------------------------------------------ derived
    def win_rate(self, i: int) -> float:
        return self.wins[i] / self.matches

    def draw_rate(self) -> float:
        return self.draws / self.matches

    def win_rate_ci(self, i: int) -> tuple[float, float]:
        """95% normal-approximation confidence interval on the win rate."""
        p, n = self.win_rate(i), self.matches
        half = 1.96 * math.sqrt(p * (1 - p) / n)
        return max(0.0, p - half), min(1.0, p + half)

    def avg(self, i: int, stat: str) -> float:
        return self.totals[i][stat] / self.matches

    def avg_possession(self, i: int) -> float:
        return self.possession_pct_sum[i] / self.matches


def _run_chunk(home: Team, away: Team, start: int, count: int, seed: int, knockout: bool) -> SimulationSummary:
    summary = SimulationSummary(names=(home.name, away.name), matches=count, knockout=knockout)
    for i in range(start, start + count):
        rng = random.Random(seed * 1_000_003 + i)
        # Alternate who is "slot 0" (first-half kickoff) so neither side gets a structural edge.
        first, second = (home, away) if i % 2 == 0 else (away, home)
        result = MatchEngine(first, second, rng, knockout=knockout, record_goals=False).play()
        summary.add(result, home_side=i % 2)
    return summary


def run_simulations(home: Team, away: Team, matches: int, seed: int = 42,
                    knockout: bool = False, workers: int = 1) -> SimulationSummary:
    if matches < 1:
        raise ValueError("matches must be >= 1")
    workers = max(1, min(workers, matches))
    if workers == 1:
        return _run_chunk(home, away, 0, matches, seed, knockout)

    chunk = math.ceil(matches / workers)
    jobs = [(s, min(chunk, matches - s)) for s in range(0, matches, chunk)]
    total = SimulationSummary(names=(home.name, away.name), matches=0, knockout=knockout)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_chunk, home, away, s, c, seed, knockout) for s, c in jobs]
        for fut in futures:
            total.merge(fut.result())
    return total
