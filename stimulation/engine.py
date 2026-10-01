"""Zone-based, event-driven match engine.

The pitch is split into 5 zones, always seen from the team on the ball:

    0 = own box   1 = own third   2 = midfield   3 = final third   4 = opponent box

Every step, the player on the ball picks an action (pass, dribble, shot...)
with weights built from their attributes and personality. The action is then
resolved as a duel against the defending team.

Calibration principle: every duel is measured RELATIVE to an average
top-flight starter (models.baseline_profile). The constants below are the
success rates two average teams get, tuned so that average-vs-average
reproduces real league numbers (data/benchmarks.json). Messi and Ronaldo then
move away from those numbers only as far as their ratings say.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .models import PlayerProfile, Team, baseline_profile

ZONES = 5
OPP_BOX = 4
SCALE = 50.0  # rating points per 1.0 of logit, anchored to real per-action rates (see benchmarks.json)

# How often each action is considered in each zone before attributes and
# personality bend the numbers.
BASE_WEIGHTS: dict[int, dict[str, float]] = {
    0: {"short_pass": 82, "long_ball": 12, "dribble": 2},
    1: {"short_pass": 78, "long_ball": 10, "dribble": 4, "through_ball": 5},
    2: {"short_pass": 70, "dribble": 6, "through_ball": 8, "long_ball": 6, "shot": 1.0},
    3: {"short_pass": 56, "dribble": 8, "through_ball": 8, "cross": 7, "shot": 3.0},
    4: {"short_pass": 40, "dribble": 9, "shot": 7, "cross": 5},
}

# Logit of success for average vs average, per zone.
PASS_BASE = {0: 3.2, 1: 2.7, 2: 2.1, 3: 1.3, 4: 0.4}
PASS_ADVANCE = {0: 0.30, 1: 0.22, 2: 0.15, 3: 0.09, 4: 0.0}
THROUGH_BASE = -0.5
DRIBBLE_BASE = 0.0         # real take-on success is ~50%
AERIAL_BASE = 0.0          # equal jumpers win half
PRESS_WEIGHT = {0: 0.55, 1: 0.45, 2: 0.3, 3: 0.15, 4: 0.1}

# Base xG for an average shooter, before chance quality / skill / keeper.
BASE_XG = {"box": 0.12, "long": 0.035, "header": 0.10, "free_kick": 0.055}

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


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def composites(p: PlayerProfile) -> dict[str, float]:
    """Raw attributes folded into the ratings the engine actually uses."""
    a, t = p.attr, p.trait
    return {
        "passing": 0.6 * a("short_passing") + 0.2 * a("ball_control") + 0.2 * a("vision"),
        # Keeping the ball when pressed: close control, not muscle.
        "press_resist": (0.35 * a("ball_control") + 0.25 * a("agility")
                         + 0.2 * a("balance") + 0.2 * a("composure")),
        "creativity": 0.6 * a("vision") + 0.25 * a("short_passing") + 0.15 * t("teamplay"),
        "movement": 0.5 * a("pace") + 0.5 * a("acceleration"),
        "dribble": (0.45 * a("dribbling") + 0.2 * a("agility")
                    + 0.2 * a("balance") + 0.15 * a("acceleration")),
        "long_pass": 0.7 * a("long_passing") + 0.3 * a("vision"),
        "crossing": a("crossing"),
        "aerial": (0.35 * a("heading") + 0.35 * a("jumping")
                   + 0.15 * a("strength") + 0.15 * p.height_score),
        "tackle_def": (0.45 * a("tackling") + 0.2 * a("strength")
                       + 0.2 * a("pace") + 0.15 * a("marking")),
        "intercept_def": 0.4 * a("interceptions") + 0.25 * a("marking") + 0.35 * t("work_rate"),
        # Winning the ball straight back after losing it (Pep's 5-second rule).
        "counterpress": 0.6 * t("work_rate") + 0.2 * a("acceleration") + 0.2 * a("stamina"),
        "finishing": 0.7 * a("finishing") + 0.3 * a("composure"),
        "long_shot": 0.6 * a("long_shots") + 0.4 * a("shot_power"),
        "header": 0.6 * a("heading") + 0.4 * a("jumping"),
        "free_kick": a("free_kicks"),
        "keeper": (0.25 * a("jumping") + 0.35 * a("agility")
                   + 0.2 * a("composure") + 0.2 * p.height_score),
    }


BASELINE = composites(baseline_profile())


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
    crosses_attempted: int = 0
    crosses_completed: int = 0
    aerials_won: int = 0
    aerials_contested: int = 0
    recoveries: int = 0
    fouls_won: int = 0
    penalties: int = 0
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


class MatchEngine:
    def __init__(self, home: Team, away: Team, rng: random.Random,
                 knockout: bool = False, record_goals: bool = True) -> None:
        self.teams = (home, away)
        self.c = (composites(home.player), composites(away.player))
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
        return 1.0 - 0.3 * progress * tiredness

    def _rel(self, side: int, key: str) -> float:
        """Rating above (+) or below (-) an average starter, after fatigue."""
        return self.c[side][key] * self._fatigue(side) - BASELINE[key]

    def _trait(self, side: int, key: str) -> float:
        return self.teams[side].player.trait(key)

    def _duel(self, attack: float, defence: float, base: float) -> float:
        """P(attacker wins). attack/defence are relative ratings; base = average vs average."""
        return sigmoid(base + (attack - defence) / SCALE)

    def _cover(self) -> float:
        """More defenders in this zone (from the formation) = harder for the attacker."""
        team = self.teams[self.dfn]
        ratio = sum(w * team.line_count(line) / BASELINE_COUNTS[line]
                    for line, w in DEFENSIVE_COVER[self.zone])
        return -0.35 * (ratio - 1.0)

    def _pressing(self) -> float:
        return -PRESS_WEIGHT[self.zone] * (self._trait(self.dfn, "work_rate") - 50) / 25

    def _crowding(self) -> float:
        """High-ego teams all want the ball in the same central spaces near goal."""
        if self.zone < 3:
            return 0.0
        return -0.35 * max(0.0, self._trait(self.att, "ego") - 50) / 50

    def _clutch_boost(self) -> float:
        if self.clock < 75 * 60:
            return 1.0
        if self.stats[self.att].goals > self.stats[self.dfn].goals:
            return 1.0
        return 1.0 + (self._trait(self.att, "clutch") - 50) / 200

    def _keeper_factor(self, high_ball: bool) -> float:
        """Multiplier on the shooter's chance from the keeper (1.0 = average real keeper)."""
        side = self.dfn
        factor = 1.0 if self.teams[side].trained_keeper else 1.3  # outfielder in goal
        factor *= 1 - (self.c[side]["keeper"] - BASELINE["keeper"]) / 150
        if high_ball:
            factor *= 1 - (self.teams[side].player.height_score - 63) / 400
        return factor

    def _advance(self, steps: int) -> None:
        self.zone = min(OPP_BOX, self.zone + steps)

    def _tick(self, lo: float, hi: float) -> None:
        dt = self.rng.uniform(lo, hi)
        self.clock += dt
        self.stats[self.att].possession_seconds += dt

    def _dead_ball(self, lo: float, hi: float) -> None:
        self.clock += self.rng.uniform(lo, hi)

    # ----------------------------------------------------- losing the ball
    def _loose_ball(self) -> None:
        """A failed pass: the side that counter-presses harder may win it straight back."""
        edge = self._rel(self.att, "counterpress") - self._rel(self.dfn, "counterpress")
        if self.rng.random() < 0.35 * sigmoid(edge / 25):
            self.stats[self.att].recoveries += 1
            return
        if self.rng.random() < 0.25:  # went out of play: throw-in for them
            self._dead_ball(6, 15)
            self._turnover(allow_counter=False)
        else:
            self._turnover()

    def _turnover(self, zone_for_new_team: int | None = None, allow_counter: bool = True) -> None:
        lost_by = self.att
        new_zone = (ZONES - 1 - self.zone) if zone_for_new_team is None else zone_for_new_team
        self.att = 1 - lost_by
        self.zone = new_zone
        self.chance_bonus = 0.0
        if allow_counter and new_zone >= 1:
            self._maybe_counter(lost_by)

    def _maybe_counter(self, lost_by: int) -> None:
        directness = 1.5 - self._trait(self.att, "patience") / 100
        exposed = 1.0 + (50 - self._trait(lost_by, "work_rate")) / 100
        p = 0.06 * math.exp(self._rel(self.att, "movement") / 40) * directness * exposed
        if self.rng.random() < p:
            self.stats[self.att].counters += 1
            self._advance(2)
            self.chance_bonus += 0.4

    # ---------------------------------------------------------- action choice
    def _choose_action(self) -> str:
        side = self.att
        p, c = self.teams[side].player, self.c[side]
        weights = dict(BASE_WEIGHTS[self.zone])

        patience = self._trait(side, "patience") / 100
        teamplay = self._trait(side, "teamplay") / 100
        selfish = self._trait(side, "selfishness") / 100
        ego = self._trait(side, "ego") / 100

        if "short_pass" in weights:
            weights["short_pass"] *= (0.5 + patience) * (0.5 + teamplay)
        if "through_ball" in weights:
            weights["through_ball"] *= (p.attr("vision") / 70) * (0.5 + teamplay)
        if "dribble" in weights:
            weights["dribble"] *= (p.attr("dribbling") / 70) ** 2
        if "long_ball" in weights:
            weights["long_ball"] *= (1.5 - patience) * (c["aerial"] / BASELINE["aerial"])
        if "cross" in weights:
            weights["cross"] *= (p.attr("crossing") / 70) * (c["aerial"] / BASELINE["aerial"]) ** 2
        if "shot" in weights:
            shot = (0.5 + selfish) * self._clutch_boost()
            if self.zone == 3:
                # Ego modifier: long-range shot demand regardless of passing lanes.
                shot *= (p.attr("long_shots") / 70) * (1 + 0.5 * ego) * (1.5 - patience)
            weights["shot"] *= shot

        roll = self.rng.random() * sum(weights.values())
        for action, w in weights.items():
            roll -= w
            if roll <= 0:
                return action
        return action

    # ----------------------------------------------------------- the actions
    def _short_pass(self) -> None:
        s = self.stats[self.att]
        s.passes_attempted += 1
        attack = 0.6 * self._rel(self.att, "passing") + 0.4 * self._rel(self.att, "press_resist")
        p = self._duel(attack, self._rel(self.dfn, "intercept_def"),
                       PASS_BASE[self.zone] + self._cover() + self._pressing() + self._crowding())
        self._tick(3, 6)
        if self.rng.random() < p:
            s.passes_completed += 1
            if self.zone == OPP_BOX:
                # 1-2s in the box sharpen the chance.
                self.chance_bonus += 0.08 * self._trait(self.att, "teamplay") / 50
            elif self.rng.random() < self._advance_chance():
                self._advance(1)
        else:
            self._loose_ball()

    def _advance_chance(self) -> float:
        """Does a completed pass move the ball forward a zone? Vision says yes,
        patience says recycle it and wait for the gap."""
        creativity = math.exp(self._rel(self.att, "creativity") / 40)
        patience = (1.3 - self._trait(self.att, "patience") / 100) / 0.8
        return PASS_ADVANCE[self.zone] * creativity * patience

    def _through_ball(self) -> None:
        s = self.stats[self.att]
        s.passes_attempted += 1
        attack = 0.6 * self._rel(self.att, "creativity") + 0.4 * self._rel(self.att, "movement")
        defence = 0.6 * self._rel(self.dfn, "intercept_def") + 0.4 * self._rel(self.dfn, "movement")
        p = self._duel(attack, defence, THROUGH_BASE + self._cover() + self._crowding())
        self._tick(3, 6)
        if self.rng.random() < p:
            s.passes_completed += 1
            self._advance(2)
            self.chance_bonus += 0.45
        else:
            self._turnover()

    def _dribble(self) -> None:
        s = self.stats[self.att]
        s.dribbles_attempted += 1
        p = self._duel(self._rel(self.att, "dribble"), self._rel(self.dfn, "tackle_def"),
                       DRIBBLE_BASE + self._cover())
        self._tick(3, 6)
        if self.rng.random() < p:
            s.dribbles_completed += 1
            self._advance(1)
            # Beating a man near goal drags defenders out of shape.
            self.chance_bonus += 0.2 if self.zone >= 3 else 0.05
            return
        foul_p = 0.10 * math.exp((self._rel(self.att, "dribble") - self._rel(self.dfn, "tackle_def")) / 40)
        if self.rng.random() < foul_p:
            self._foul_won()
        else:
            self._turnover()

    def _long_ball(self) -> None:
        s = self.stats[self.att]
        s.passes_attempted += 1
        self._tick(4, 8)
        accurate = self.rng.random() < 0.55 + self._rel(self.att, "long_pass") / 150
        if accurate and self._aerial_duel():
            s.passes_completed += 1
            self.zone = max(self.zone, 3)
        else:
            self._turnover(zone_for_new_team=1)

    def _cross(self, set_piece: bool = False) -> None:
        s = self.stats[self.att]
        if not set_piece:
            s.crosses_attempted += 1
            s.passes_attempted += 1
        self._tick(3, 6)
        delivery = (0.62 if set_piece else 0.5) + self._rel(self.att, "crossing") / 150
        claim = 0.10 + (self.teams[self.dfn].player.height_score - 63) / 600
        if self.rng.random() < delivery and self.rng.random() > claim and self._aerial_duel():
            if not set_piece:
                s.crosses_completed += 1
                s.passes_completed += 1
            if self.rng.random() < 0.75:
                self._shoot("header")
            else:  # knocked down in the box
                self.zone = OPP_BOX
                self.chance_bonus += 0.2
        elif self.rng.random() < 0.25:
            self._corner()
        else:
            self._dead_ball(5, 15)
            self._turnover(zone_for_new_team=self.rng.choice((0, 1)), allow_counter=False)

    def _aerial_duel(self) -> bool:
        st = self.stats
        st[0].aerials_contested += 1
        st[1].aerials_contested += 1
        won = self.rng.random() < self._duel(self._rel(self.att, "aerial"), self._rel(self.dfn, "aerial"), AERIAL_BASE)
        st[self.att if won else self.dfn].aerials_won += 1
        return won

    def _corner(self) -> None:
        self.stats[self.att].corners += 1
        self._dead_ball(20, 35)
        # Teams that can't win headers play it short and keep the ball.
        if self._rel(self.att, "aerial") < -5 and self.rng.random() < 0.6:
            self.zone = 3
            return
        self._cross(set_piece=True)

    def _foul_won(self) -> None:
        self.stats[self.att].fouls_won += 1
        self._dead_ball(15, 30)
        if self.zone == OPP_BOX and self.rng.random() < 0.45:
            self._penalty()
        elif self.zone >= 3:
            direct = 0.4 + self._rel(self.att, "free_kick") / 100
            if self.rng.random() < direct:
                self._shoot("free_kick")
            else:
                self._cross(set_piece=True)
        # Elsewhere: quick free kick, the move carries on in the same zone.

    def _penalty_p(self) -> float:
        # 0.76 = average conversion; taker skill and keeper move it.
        pen = self.teams[self.att].player.attr("penalties")
        return 0.76 + (pen - 70) / 160 + (self._keeper_factor(False) - 1) * 0.2

    def _penalty(self) -> None:
        self.stats[self.att].penalties += 1
        self._resolve_shot("penalty", xg=0.76, p_goal=self._penalty_p())

    def _shoot(self, kind: str | None = None) -> None:
        if kind is None:
            kind = "box" if self.zone == OPP_BOX else "long"
        skill_key = {"box": "finishing", "long": "long_shot", "header": "header", "free_kick": "free_kick"}[kind]
        skill = math.exp(self._rel(self.att, skill_key) / 60)
        xg = min(BASE_XG[kind] * (1 + self.chance_bonus) * skill, 0.8)
        self._tick(2, 4)
        p_goal = xg * self._keeper_factor(high_ball=kind != "box") * self._clutch_boost()
        self._resolve_shot(kind, xg=xg, p_goal=p_goal)

    def _resolve_shot(self, kind: str, xg: float, p_goal: float) -> None:
        s = self.stats[self.att]
        s.shots += 1
        s.xg += xg
        if self.rng.random() < p_goal:
            s.shots_on_target += 1
            self._goal(kind)
            return
        miss = self.rng.random()
        if miss < 0.30:  # saved
            s.shots_on_target += 1
            if self.rng.random() < 0.3:
                self._corner()
                return
        elif miss < 0.55 and kind != "penalty":  # blocked
            if self.rng.random() < 0.35:
                self._corner()
                return
        self._dead_ball(10, 25)
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
        self._dead_ball(40, 70)
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
            self.att = taker
            return self.rng.random() < self._penalty_p() - 0.02  # shootout pressure
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
