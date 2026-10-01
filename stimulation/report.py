"""Turns results into readable terminal output or JSON-ready dicts."""

from __future__ import annotations

from .engine import MatchResult
from .monte_carlo import STAT_FIELDS, SimulationSummary

KIND_LABELS = {
    "box": "inside the box",
    "long": "long range",
    "header": "header",
    "free_kick": "direct free kick",
    "penalty": "penalty",
}


def _bar(pct: float, width: int = 30) -> str:
    filled = round(pct / 100 * width)
    return "#" * filled + "." * (width - filled)


def format_summary(s: SimulationSummary) -> str:
    a, b = s.names
    lines = [
        f"{a}  vs  {b}",
        f"{s.matches:,} simulated matches" + (" (knockout: extra time + penalties)" if s.knockout else ""),
        "",
        "RESULTS",
    ]
    for i, name in enumerate(s.names):
        lo, hi = s.win_rate_ci(i)
        pct = 100 * s.win_rate(i)
        lines.append(f"  {name:<22} wins {pct:5.1f}%  [{_bar(pct)}]  (95% CI {100*lo:.1f}-{100*hi:.1f}%)")
    if not s.knockout:
        pct = 100 * s.draw_rate()
        lines.append(f"  {'Draw':<22}      {pct:5.1f}%  [{_bar(pct)}]")
    else:
        lines.append(f"  Went to penalties: {100 * s.shootouts / s.matches:.1f}%")

    lines += ["", "AVERAGE MATCH", f"  {'':<22}{a[:16]:>16}{b[:16]:>16}"]
    rows = [
        ("Goals", lambda i: f"{s.avg(i, 'goals'):.2f}"),
        ("xG", lambda i: f"{s.avg(i, 'xg'):.2f}"),
        ("Possession", lambda i: f"{s.avg_possession(i):.1f}%"),
        ("Shots", lambda i: f"{s.avg(i, 'shots'):.1f}"),
        ("Shots on target", lambda i: f"{s.avg(i, 'shots_on_target'):.1f}"),
        ("Pass accuracy", lambda i: f"{_ratio(s, i, 'passes_completed', 'passes_attempted'):.1f}%"),
        ("Passes", lambda i: f"{s.avg(i, 'passes_attempted'):.0f}"),
        ("Dribble success", lambda i: f"{_ratio(s, i, 'dribbles_completed', 'dribbles_attempted'):.1f}%"),
        ("Aerial duels won", lambda i: f"{s.avg(i, 'aerials_won'):.1f}"),
        ("Fouls won", lambda i: f"{s.avg(i, 'fouls_won'):.1f}"),
        ("Corners", lambda i: f"{s.avg(i, 'corners'):.1f}"),
        ("Counter-attacks", lambda i: f"{s.avg(i, 'counters'):.1f}"),
    ]
    for label, fn in rows:
        lines.append(f"  {label:<22}{fn(0):>16}{fn(1):>16}")

    lines += ["", "HOW THE GOALS CAME"]
    for i, name in enumerate(s.names):
        total = sum(s.goal_types[i].values()) or 1
        parts = ", ".join(f"{KIND_LABELS[k]} {100 * v / total:.0f}%"
                          for k, v in s.goal_types[i].most_common())
        lines.append(f"  {name}: {parts}")

    lines += ["", "MOST COMMON SCORELINES"]
    for (ga, gb), n in s.scorelines.most_common(6):
        lines.append(f"  {ga}-{gb}  {100 * n / s.matches:4.1f}%")
    for i, name in enumerate(s.names):
        bw = s.biggest_win[i]
        if bw:
            score = f"{bw[0]}-{bw[1]}" if i == 0 else f"{bw[1]}-{bw[0]}"
            lines.append(f"  Biggest {name} win: {score}")
    return "\n".join(lines)


def _ratio(s: SimulationSummary, i: int, num: str, den: str) -> float:
    d = s.totals[i][den]
    return 100 * s.totals[i][num] / d if d else 0.0


def summary_to_dict(s: SimulationSummary) -> dict:
    return {
        "teams": list(s.names),
        "matches": s.matches,
        "knockout": s.knockout,
        "wins": dict(zip(s.names, s.wins)),
        "draws": s.draws,
        "shootouts": s.shootouts,
        "win_rate": {n: s.win_rate(i) for i, n in enumerate(s.names)},
        "win_rate_95ci": {n: s.win_rate_ci(i) for i, n in enumerate(s.names)},
        "averages": {
            n: {**{f: s.avg(i, f) for f in STAT_FIELDS}, "possession_pct": s.avg_possession(i)}
            for i, n in enumerate(s.names)
        },
        "goal_types": {n: dict(s.goal_types[i]) for i, n in enumerate(s.names)},
        "top_scorelines": [{"score": f"{a}-{b}", "count": c} for (a, b), c in s.scorelines.most_common(10)],
    }


def format_match(m: MatchResult) -> str:
    a, b = m.names
    head = f"{a} {m.goals[0]} - {m.goals[1]} {b}"
    if m.shootout:
        head += f"  ({m.shootout[0]}-{m.shootout[1]} on penalties)"
    lines = [head, ""]
    for g in m.goal_log:
        lines.append(f"  {g.minute:>3}'  {m.names[g.team]} #{g.role} - {KIND_LABELS[g.kind]}")
    if not m.goal_log:
        lines.append("  No goals.")
    s0, s1 = m.stats
    lines += [
        "",
        f"  Possession   {m.possession_pct(0):5.1f}% - {m.possession_pct(1):.1f}%",
        f"  Shots        {s0.shots:>5} - {s1.shots}",
        f"  On target    {s0.shots_on_target:>5} - {s1.shots_on_target}",
        f"  xG           {s0.xg:5.2f} - {s1.xg:.2f}",
        f"  Corners      {s0.corners:>5} - {s1.corners}",
    ]
    return "\n".join(lines)
