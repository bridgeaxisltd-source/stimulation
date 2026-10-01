"""Zone-based, event-driven match engine.

The pitch is split into 5 zones, always seen from the team on the ball:

    0 = own box   1 = own third   2 = midfield   3 = final third   4 = opponent box

Every step, the player on the ball picks an action (pass, dribble, shot...)
using weights built from their attributes and personality. The action is then
resolved as a probability contest against the defending team. A lost ball
flips possession, and the zone is mirrored (zone z for us is 4 - z for them).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .models import Team

ZONES = 5
OPP_BOX = 4

# How often each action is considered in each zone before attributes and
# personality bend the numbers.
BASE_WEIGHTS: dict[int, dict[str, float]] = {
    0: {"short_pass": 70, "long_ball": 18, "dribble": 12},
    1: {"short_pass": 62, "long_ball": 14, "dribble": 18, "through_ball": 6},
    2: {"short_pass": 55, "dribble": 20, "through_ball": 12, "long_ball": 8, "shot": 1.5},
    3: {"short_pass": 44, "dribble": 22, "through_ball": 12, "cross": 10, "shot": 4},
    4: {"short_pass": 36, "dribble": 18, "shot": 16, "cross": 8},
}

# Base xG before skill / keeper adjustments.
BASE_XG = {
    "box": 0.10,
    "long": 0.03,
    "header": 0.09,
    "free_kick": 0.055,
}

# Which roles are most likely to finish each type of chance.
SCORER_LINE_WEIGHTS = {
    "box": {"FWD": 6, "MID": 3, "DEF": 1},
    "long": {"FWD": 3, "MID": 5, "DEF": 1},
    "header": {"FWD": 4, "MID": 2, "DEF": 4},
    "free_kick": {"FWD": 5, "MID": 4, "DEF": 1},
    "penalty": {"FWD": 8, "MID": 2, "DEF": 0},
}

# Defenders that contest an attacker in each zone, as (line, weight).
DEFENSIVE_COVER = {
    0: (("FWD", 1.0),),
    1: (("FWD", 0.6), ("MID", 0.4)),
    2: (("MID", 1.0),),
    3: (("MID", 0.4), ("DEF", 0.6)),
    4: (("DEF", 1.0),),
}
BASELINE_COUNTS = {"FWD": 3, "MID": 3, "DEF": 4}  # 4-3-3 is "neutral"

# The closer to goal, the more bodies are behind the ball: a flat logit
# penalty on every attacking action in that zone.
ZONE_CONGESTION = {0: 0.0, 1: 0.0, 2: -0.1, 3: -0.5, 4: -1.0}


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class TeamStats:
    goals: int = 0
    shots: int = 0
    shots_on_target: int = 0
    xg: float = 0.0
    possession_seconds: float = 0.0
    passes_attempted: int = 0
    passes_completed: int = 0
    dribbles_attempted: int = 0
    dribbles_completed: int = 0
    aerials_won: int = 0
    aerials_contested: int = 0
    fouls_won: int = 0
    corners: int = 0
    counters: int = 0
    goal_types: dict[str, int] = field(default_factory=dict)


@dataclass
class GoalEvent:
    minute: int
    team: int
    role: str
    kind: str


@dataclass
class MatchResult:
    names: tuple[str, str]
    goals: tuple[int, int]
    stats: tuple[TeamStats, TeamStats]
    goal_log: list[GoalEvent]
    shootout: tuple[int, int] | None = None

    @property
    def winner(self) -> int | None:
        """0 or 1, or None for a draw."""
        if self.goals[0] != self.goals[1]:
            return 0 if self.goals[0] > self.goals[1] else 1
        if self.shootout:
            return 0 if self.shootout[0] > self.shootout[1] else 1
        return None

    def possession_pct(self, team: int) -> float:
        total = self.stats[0].possession_seconds + self.stats[1].possession_seconds
        return 100.0 * self.stats[team].possession_seconds / total if total else 50.0


class _Ratings:
    """Composite ratings derived once per team from raw attributes."""

    def __init__(self, team: Team) -> None:
        p = team.player
        a, t = p.attr, p.trait
        self.passing = 0.6 * a("short_passing") + 0.25 * a("ball_control") + 0.15 * a("vision")
        self.creativity = 0.5 * a("vision") + 0.3 * a("short_passing") + 0.2 * t("teamplay")
        self.movement = 0.5 * a("pace") + 0.5 * a("acceleration")
        self.dribble = (0.45 * a("dribbling") + 0.2 * a("agility")
                        + 0.2 * a("balance") + 0.15 * a("acceleration"))
        self.long_pass = 0.7 * a("long_passing") + 0.3 * a("vision")
        self.crossing = a("crossing")
        self.aerial = (0.35 * a("heading") + 0.35 * a("jumping")
                       + 0.15 * a("strength") + 0.15 * p.height_score)
        self.tackle_def = (0.45 * a("tackling") + 0.2 * a("strength")
                           + 0.2 * a("pace") + 0.15 * a("marking"))
        self.intercept_def = (0.5 * a("interceptions") + 0.3 * a("marking")
                              + 0.2 * t("work_rate"))
        self.finishing = 0.7 * a("finishing") + 0.3 * a("composure")
        self.long_shot = 0.6 * a("long_shots") + 0.4 * a("shot_power")
        self.header = 0.6 * a("heading") + 0.4 * a("jumping")
        # Nobody here is a trained keeper: 0.6 is the "outfield player in goal" penalty.
        self.keeper = 0.6 * (0.25 * a("jumping") + 0.35 * a("agility")
                             + 0.2 * a("composure") + 0.2 * p.height_score)
        self.reach = p.height_score


class MatchEngine:
    def __init__(self, home: Team, away: Team, rng: random.Random,
                 knockout: bool = False, record_goals: bool = True) -> None:
        self.teams = (home, away)
        self.r = (_Ratings(home), _Ratings(away))
        self.rng = rng
        self.knockout = knockout
        self.record_goals = record_goals

        self.stats = (TeamStats(), TeamStats())
        self.goal_log: list[GoalEvent] = []
        self.clock = 0.0          # seconds
        self.period_end = 0.0
        self.minutes_played = 90  # 120 if extra time
        self.att = 0              # team index on the ball
        self.zone = 2
        self.chance_bonus = 0.0   # quality built up in the current move

    # ------------------------------------------------------------------ helpers
    @property
    def dfn(self) -> int:
        return 1 - self.att

    @property
    def minute(self) -> int:
        return int(self.clock // 60) + 1

    def _fatigue(self, side: int) -> float:
        """1.0 at kickoff, drifting down as the game goes on."""
        p = self.teams[side].player
        progress = min(self.clock / (self.minutes_played * 60), 1.0)
        tiredness = (1 - p.attr("stamina") / 100) * (0.6 + p.trait("work_rate") / 100)
        return 1.0 - 0.35 * progress * tiredness

    def _trait(self, side: int, key: str) -> float:
        return self.teams[side].player.trait(key)

    def _contest(self, attack: float, defence: float, base: float) -> float:
        """Probability that the attacking side wins a duel, from ratings on ~0-100."""
        return sigmoid(base + (attack * self._fatigue(self.att)
                               - defence * self._fatigue(self.dfn) - 50) / 25)

    def _cover(self) -> float:
        """Logit penalty for the attacker based on how many defenders cover this zone."""
        team = self.teams[self.dfn]
        ratio = sum(w * team.line_count(line) / BASELINE_COUNTS[line]
                    for line, w in DEFENSIVE_COVER[self.zone])
        return ZONE_CONGESTION[self.zone] - 0.35 * (ratio - 1.0)

    def _pressing(self) -> float:
        """High press: only bites when the attacker is building from the back."""
        if self.zone > 1:
            return 0.0
        return -0.9 * (self._trait(self.dfn, "work_rate") - 50) / 100

    def _crowding(self) -> float:
        """High-ego teams all want the ball in the same central spaces near goal."""
        if self.zone < 3:
            return 0.0
        return -0.4 * max(0.0, self._trait(self.att, "ego") - 50) / 50

    def _clutch_boost(self) -> float:
        if self.clock < 75 * 60:
            return 1.0
        mine, theirs = self.stats[self.att].goals, self.stats[self.dfn].goals
        if mine > theirs:
            return 1.0
        return 1.0 + (self._trait(self.att, "clutch") - 50) / 150

    def _advance(self, steps: int) -> None:
        self.zone = min(OPP_BOX, self.zone + steps)

    def _turnover(self, zone_for_new_team: int | None = None, allow_counter: bool = True) -> None:
        old = self.att
        new_zone = (ZONES - 1 - self.zone) if zone_for_new_team is None else zone_for_new_team
        self.att = 1 - old
        self.zone = new_zone
        self.chance_bonus = 0.0
        if allow_counter and new_zone >= 1:
            self._maybe_counter(old)

    def _maybe_counter(self, lost_by: int) -> None:
        r = self.r[self.att]
        directness = 1.5 - self._trait(self.att, "patience") / 100
        exposed = 1.0 + (50 - self._trait(lost_by, "work_rate")) / 100
        p = 0.16 * (r.movement / 90) * directness * exposed
        if self.rng.random() < p:
            self.stats[self.att].counters += 1
            self._advance(2)
            self.chance_bonus += 0.35

    def _tick(self, lo: float, hi: float, live: bool = True) -> None:
        dt = self.rng.uniform(lo, hi)
        self.clock += dt
        if live:
            self.stats[self.att].possession_seconds += dt

    # ---------------------------------------------------------- action choice
    def _choose_action(self) -> str:
        p, t = self.teams[self.att].player, self._trait
        side = self.att
        weights = dict(BASE_WEIGHTS[self.zone])

        patience = t(side, "patience") / 100
        teamplay = t(side, "teamplay") / 100
        selfish = t(side, "selfishness") / 100
        ego = t(side, "ego") / 100

        if "short_pass" in weights:
            weights["short_pass"] *= (p.attr("short_passing") / 80) * (0.5 + patience) * (0.5 + teamplay)
        if "through_ball" in weights:
            weights["through_ball"] *= (p.attr("vision") / 80) * (0.5 + teamplay)
        if "dribble" in weights:
            weights["dribble"] *= (p.attr("dribbling") / 80) ** 2
        if "long_ball" in weights:
            weights["long_ball"] *= (p.attr("long_passing") / 80) * (1.5 - patience) * (0.4 + self.r[side].aerial / 100)
        if "cross" in weights:
            weights["cross"] *= (p.attr("crossing") / 80) * (self.r[side].aerial / 70) ** 2
        if "shot" in weights:
            shot = (0.6 + selfish) * self._clutch_boost()
            if self.zone == 3:
                # The "ego modifier": long-range shot demand regardless of passing lanes.
                shot *= (p.attr("long_shots") / 80) * (1 + 0.5 * ego) * (1.4 - patience)
            weights["shot"] *= shot

        roll = self.rng.random() * sum(weights.values())
        for action, w in weights.items():
            roll -= w
            if roll <= 0:
                return action
        return action

    # ----------------------------------------------------------- the actions
    def _short_pass(self) -> None:
        s, r, rd = self.stats[self.att], self.r[self.att], self.r[self.dfn]
        s.passes_attempted += 1
        p = self._contest(r.passing, rd.intercept_def,
                          1.7 + self._cover() + self._pressing() + self._crowding())
        self._tick(2, 5)
        if self.rng.random() < p:
            s.passes_completed += 1
            if self.zone == OPP_BOX:
                self.chance_bonus += 0.12 * self._trait(self.att, "teamplay") / 80  # 1-2s in the box
            elif self.rng.random() < 0.3 * r.creativity / 85:
                self._advance(1)
        else:
            self._turnover()

    def _through_ball(self) -> None:
        s, r, rd = self.stats[self.att], self.r[self.att], self.r[self.dfn]
        s.passes_attempted += 1
        attack = 0.6 * r.creativity + 0.4 * r.movement
        defence = 0.7 * rd.intercept_def + 0.3 * self.teams[self.dfn].player.attr("pace")
        p = self._contest(attack, defence, 0.0 + self._cover() + self._crowding())
        self._tick(3, 6)
        if self.rng.random() < p:
            s.passes_completed += 1
            self._advance(2)
            self.chance_bonus += 0.45
        else:
            self._turnover()

    def _dribble(self) -> None:
        s, r, rd = self.stats[self.att], self.r[self.att], self.r[self.dfn]
        s.dribbles_attempted += 1
        p = self._contest(r.dribble, rd.tackle_def, 0.3 + self._cover())
        self._tick(3, 6)
        if self.rng.random() < p:
            s.dribbles_completed += 1
            self._advance(1)
            self.chance_bonus += 0.15
            return
        # Lost the duel: either a foul (great dribblers draw loads) or a turnover.
        foul_p = 0.14 * (self.teams[self.att].player.attr("dribbling") / 85) \
            * (1 + (60 - self.teams[self.dfn].player.attr("tackling")) / 100)
        if self.rng.random() < foul_p:
            self._foul_won()
        else:
            self._turnover()

    def _long_ball(self) -> None:
        r, rd = self.r[self.att], self.r[self.dfn]
        self.stats[self.att].passes_attempted += 1
        self._tick(4, 8)
        accurate = self.rng.random() < 0.45 + r.long_pass / 250
        if accurate and self._aerial_duel():
            self.stats[self.att].passes_completed += 1
            self.zone = max(self.zone, 3)
        else:
            # Defending team wins it in their own third.
            self._turnover(zone_for_new_team=1)

    def _cross(self, set_piece: bool = False) -> None:
        r = self.r[self.att]
        if not set_piece:
            self.stats[self.att].passes_attempted += 1
        self._tick(3, 6)
        accurate = self.rng.random() < (0.55 if set_piece else 0.35) + r.crossing / 400
        # The keeper can come and claim it.
        claim = 0.08 + self.r[self.dfn].reach / 1000
        if accurate and self.rng.random() > claim and self._aerial_duel():
            if not set_piece:
                self.stats[self.att].passes_completed += 1
            self._shoot("header")
        elif self.rng.random() < 0.25:
            self._corner()
        else:
            self._turnover(zone_for_new_team=0, allow_counter=False)

    def _aerial_duel(self) -> bool:
        s = self.stats
        s[0].aerials_contested += 1
        s[1].aerials_contested += 1
        won = self.rng.random() < self._contest(self.r[self.att].aerial, self.r[self.dfn].aerial, 0.6)
        s[self.att if won else self.dfn].aerials_won += 1
        return won

    def _corner(self) -> None:
        self.stats[self.att].corners += 1
        self._tick(20, 35, live=False)
        # Teams with no aerial threat play it short instead of lumping it in.
        if self.r[self.att].aerial < 70 and self.rng.random() < 0.55:
            self.zone = 3
            return
        self._cross(set_piece=True)

    def _foul_won(self) -> None:
        self.stats[self.att].fouls_won += 1
        self._tick(15, 30, live=False)
        if self.zone == OPP_BOX and self.rng.random() < 0.18:
            self._penalty()
        elif self.zone >= 3:
            direct = 0.4 + (self.teams[self.att].player.attr("free_kicks") - 80) / 100
            if self.rng.random() < direct:
                self._shoot("free_kick")
            else:
                self._cross(set_piece=True)
        # Elsewhere: free kick restarts the move in the same zone.

    def _penalty(self) -> None:
        taker = self.teams[self.att].player
        p_goal = 0.52 + taker.attr("penalties") / 330 - (self.r[self.dfn].keeper - 50) / 400
        self._resolve_shot("penalty", xg=0.76, p_goal=p_goal)

    def _shoot(self, kind: str | None = None) -> None:
        if kind is None:
            kind = "box" if self.zone == OPP_BOX else "long"
        r, rd = self.r[self.att], self.r[self.dfn]
        skill = {
            "box": r.finishing,
            "long": r.long_shot,
            "header": r.header,
            "free_kick": self.teams[self.att].player.attr("free_kicks"),
        }[kind] * self._fatigue(self.att)
        xg = BASE_XG[kind] * (1 + self.chance_bonus) * (skill / 85) ** 2
        xg = min(xg, 0.85)
        keeper = 1.35 - rd.keeper / 150
        if kind in ("long", "header", "free_kick"):
            keeper *= 1.1 - rd.reach / 500  # height matters for high/far shots
        self._tick(3, 6)
        self._resolve_shot(kind, xg=xg, p_goal=xg * keeper * self._clutch_boost())

    def _resolve_shot(self, kind: str, xg: float, p_goal: float) -> None:
        s = self.stats[self.att]
        s.shots += 1
        s.xg += xg
        roll = self.rng.random()
        if roll < p_goal:
            s.shots_on_target += 1
            self._goal(kind)
            return
        # Missed: saved, blocked or off target.
        miss = self.rng.random()
        if miss < 0.35:
            s.shots_on_target += 1
            if self.rng.random() < 0.35:
                self._corner()
                return
        elif miss < 0.55 and kind != "penalty" and self.rng.random() < 0.4:
            self._corner()
            return
        self._turnover(zone_for_new_team=0, allow_counter=False)

    def _goal(self, kind: str) -> None:
        s = self.stats[self.att]
        s.goals += 1
        s.goal_types[kind] = s.goal_types.get(kind, 0) + 1
        if self.record_goals:
            team = self.teams[self.att]
            weights = SCORER_LINE_WEIGHTS[kind]
            lines = [ln for ln in weights if weights[ln] > 0]
            line = self.rng.choices(lines, weights=[weights[ln] for ln in lines])[0]
            role = self.rng.choice(team.line(line))
            self.goal_log.append(GoalEvent(self.minute, self.att, role, kind))
        self._tick(40, 70, live=False)
        # Conceding team kicks off.
        self.att = self.dfn
        self.zone = 2
        self.chance_bonus = 0.0

    # --------------------------------------------------------------- the match
    def _play_period(self, start_min: int, length_min: int, kickoff: int, stoppage: tuple[int, int]) -> None:
        self.clock = start_min * 60
        self.period_end = (start_min + length_min) * 60 + self.rng.uniform(*stoppage) * 60
        self.att, self.zone, self.chance_bonus = kickoff, 2, 0.0
        actions = {
            "short_pass": self._short_pass,
            "through_ball": self._through_ball,
            "dribble": self._dribble,
            "long_ball": self._long_ball,
            "cross": self._cross,
            "shot": self._shoot,
        }
        while self.clock < self.period_end:
            actions[self._choose_action()]()

    def _shootout(self) -> tuple[int, int]:
        def kick(taker: int) -> bool:
            p = self.teams[taker].player.attr("penalties")
            keeper = self.r[1 - taker].keeper
            return self.rng.random() < 0.5 + p / 330 - (keeper - 50) / 400
        score = [0, 0]
        for i in range(5):
            for side in (0, 1):
                score[side] += kick(side)
                remaining = [5 - i - (1 if s <= side else 0) for s in (0, 1)]
                if score[0] + remaining[0] < score[1] or score[1] + remaining[1] < score[0]:
                    return score[0], score[1]
        while score[0] == score[1]:
            a, b = kick(0), kick(1)
            score[0] += a
            score[1] += b
        return score[0], score[1]

    def play(self) -> MatchResult:
        self._play_period(0, 45, kickoff=0, stoppage=(1, 4))
        self._play_period(45, 45, kickoff=1, stoppage=(2, 6))
        shootout = None
        if self.knockout and self.stats[0].goals == self.stats[1].goals:
            self.minutes_played = 120
            self._play_period(90, 15, kickoff=0, stoppage=(0, 2))
            self._play_period(105, 15, kickoff=1, stoppage=(0, 3))
            if self.stats[0].goals == self.stats[1].goals:
                shootout = self._shootout()
        return MatchResult(
            names=(self.teams[0].name, self.teams[1].name),
            goals=(self.stats[0].goals, self.stats[1].goals),
            stats=self.stats,
            goal_log=self.goal_log,
            shootout=shootout,
        )
