"""Turns real stats (messivsronaldo.app) into 0-100 engine ratings.

Every derived rating comes from one stat mapped through a piecewise-linear
scale. The scale "anchors" are the judgement calls: e.g. 2.0 successful
dribbles per 90 = 85 dribbling, 4.5 = 99. Change an anchor here and every
rating that uses it moves, with the reason printed next to it.

Ratings with no stat behind them (pace, strength, tackling, ego, patience,
work rate...) stay as the hand estimates from players.json and are reported
as "estimate", so it is always clear which numbers are data and which are not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .models import PlayerProfile

DEFAULT_STATS_PATH = Path(__file__).resolve().parent.parent / "data" / "stats" / "messivsronaldo_detailed.json"


def interpolate(x: float, anchors: list[tuple[float, float]]) -> float:
    """Piecewise-linear lookup, clamped at both ends."""
    if x <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return anchors[-1][1]


def _minutes(s: dict) -> float:
    """Minutes behind the 'league + UCL since 09/10' sample, recovered from key passes."""
    return s["key_passes"]["total"] / s["key_passes"]["per90"] * 90


def _shots_per90(s: dict) -> float:
    return s["shots"]["total"] / _minutes(s) * 90


def _big_game_ga_per90(s: dict) -> float:
    finals = 90 / s["finals_goal_contributions"]["minutes_per"]
    ko = 90 / s["ucl_knockout_goal_contributions"]["minutes_per"]
    return (finals + ko) / 2


@dataclass(frozen=True)
class Rule:
    block: str        # "attributes" or "personality"
    key: str
    stat_label: str
    stat: Callable[[dict], float]
    anchors: list[tuple[float, float]]
    fmt: str = "{:.2f}"


RULES: list[Rule] = [
    Rule("attributes", "dribbling", "successful dribbles /90",
         lambda s: s["successful_dribbles"]["per90"], [(0.5, 60), (2.0, 85), (4.5, 99)]),
    Rule("attributes", "vision", "accurate through balls /90",
         lambda s: s["accurate_throughballs"]["per90"], [(0.05, 65), (0.3, 85), (0.8, 98)]),
    Rule("attributes", "short_passing", "key passes /90",
         lambda s: s["key_passes"]["per90"], [(0.5, 65), (1.5, 82), (2.5, 95)]),
    Rule("attributes", "finishing", "goals per shot",
         lambda s: 1 / s["shots"]["shots_per_goal"], [(0.10, 70), (0.15, 85), (0.20, 96)], "{:.3f}"),
    Rule("attributes", "composure", "goals above xG (share of xG)",
         lambda s: s["xg"]["goals_minus_xg"] / s["xg"]["total"], [(-0.05, 75), (0.0, 85), (0.15, 97)], "{:+.1%}"),
    Rule("attributes", "long_shots", "open-play goals from outside the box per game",
         lambda s: 1 / s["outside_box_goals_open_play"]["games_per"], [(0.02, 60), (0.05, 82), (0.10, 96)], "{:.3f}"),
    Rule("attributes", "free_kicks", "free-kick goals per game",
         lambda s: 1 / s["free_kick_goals"]["games_per"], [(0.01, 60), (0.05, 85), (0.07, 95)], "{:.3f}"),
    Rule("attributes", "penalties", "penalty conversion",
         lambda s: s["penalties"]["scored"] / s["penalties"]["taken"], [(0.65, 60), (0.75, 78), (0.85, 92)], "{:.1%}"),
    Rule("attributes", "heading", "aerial duels won /90",
         lambda s: s["aerial_duels_won"]["per90"], [(0.1, 45), (1.0, 80), (2.5, 95)]),
    Rule("personality", "selfishness", "shots share of (shots + key passes)",
         lambda s: _shots_per90(s) / (_shots_per90(s) + s["key_passes"]["per90"]), [(0.5, 30), (0.8, 90)], "{:.1%}"),
    Rule("personality", "teamplay", "big chances created /90",
         lambda s: s["big_chances_created"]["per90"], [(0.1, 50), (0.4, 78), (0.8, 95)]),
    Rule("personality", "clutch", "goals+assists /90 in finals & UCL knockouts",
         _big_game_ga_per90, [(0.5, 60), (1.0, 95)]),
]


@dataclass(frozen=True)
class Provenance:
    block: str
    key: str
    value: float
    source: str  # "estimate" or "derived: <stat> = <value>"


def load_stats(path: str | Path = DEFAULT_STATS_PATH) -> dict[str, dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["players"]


def derive_player(player: PlayerProfile, stats: dict) -> tuple[PlayerProfile, list[Provenance]]:
    attributes, personality = dict(player.attributes), dict(player.personality)
    derived: dict[tuple[str, str], str] = {}
    for rule in RULES:
        raw = rule.stat(stats)
        value = round(interpolate(raw, rule.anchors))
        (attributes if rule.block == "attributes" else personality)[rule.key] = value
        derived[(rule.block, rule.key)] = f"derived: {rule.stat_label} = {rule.fmt.format(raw)}"

    provenance = [
        Provenance(block, key, block_values[key], derived.get((block, key), "estimate"))
        for block, block_values in (("attributes", attributes), ("personality", personality))
        for key in block_values
    ]
    era = "career, all-time stats"
    return replace(player, era=era, attributes=attributes, personality=personality), provenance


def apply_stats(players: dict[str, PlayerProfile], stats_path: str | Path = DEFAULT_STATS_PATH
                ) -> tuple[dict[str, PlayerProfile], dict[str, list[Provenance]]]:
    """Returns players with data-backed ratings swapped in, plus where each number came from."""
    stats = load_stats(stats_path)
    out, report = dict(players), {}
    for pid, s in stats.items():
        if pid in players:
            out[pid], report[pid] = derive_player(players[pid], s)
    return out, report


def format_provenance(players: dict[str, PlayerProfile], report: dict[str, list[Provenance]]) -> str:
    lines = []
    for pid, rows in report.items():
        lines.append(f"{players[pid].name} ({players[pid].era})")
        for row in rows:
            lines.append(f"  {row.block[:4]}.{row.key:<15} {row.value:>5.0f}   {row.source}")
        derived = sum(r.source != "estimate" for r in rows)
        lines.append(f"  -> {derived}/{len(rows)} ratings come from data, the rest are estimates\n")
    return "\n".join(lines)
