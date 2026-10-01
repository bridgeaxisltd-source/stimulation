"""Data models: player profiles, formations and teams."""

from __future__ import annotations

from dataclasses import dataclass

ATTRIBUTE_KEYS = (
    "pace", "acceleration", "dribbling", "ball_control", "agility", "balance",
    "short_passing", "long_passing", "vision", "crossing",
    "finishing", "shot_power", "long_shots", "heading", "jumping", "strength",
    "stamina", "tackling", "interceptions", "marking",
    "free_kicks", "penalties", "composure",
)

PERSONALITY_KEYS = (
    "selfishness",  # how often they pick a shot over a pass
    "ego",          # long-range shot demand + crowding the same central spaces
    "patience",     # willingness to recycle possession instead of forcing it
    "teamplay",     # instinct to combine (1-2s, through balls)
    "work_rate",    # pressing / tracking back, costs stamina
    "clutch",       # boost when the game is on the line late on
)

# Role names per line, used to label who scored (all 11 are the same player,
# so the role is the only thing that tells them apart).
FORMATIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "4-3-3": {
        "GK": ("GK",),
        "DEF": ("RB", "RCB", "LCB", "LB"),
        "MID": ("RCM", "CDM", "LCM"),
        "FWD": ("RW", "ST", "LW"),
    },
    "4-4-2": {
        "GK": ("GK",),
        "DEF": ("RB", "RCB", "LCB", "LB"),
        "MID": ("RM", "RCM", "LCM", "LM"),
        "FWD": ("RS", "LS"),
    },
    "3-5-2": {
        "GK": ("GK",),
        "DEF": ("RCB", "CB", "LCB"),
        "MID": ("RWB", "RCM", "CDM", "LCM", "LWB"),
        "FWD": ("RS", "LS"),
    },
    "4-2-3-1": {
        "GK": ("GK",),
        "DEF": ("RB", "RCB", "LCB", "LB"),
        "MID": ("RDM", "LDM", "RAM", "CAM", "LAM"),
        "FWD": ("ST",),
    },
}


@dataclass(frozen=True)
class PlayerProfile:
    id: str
    name: str
    era: str
    height_cm: int
    attributes: dict[str, int]
    personality: dict[str, int]
    reference: dict | None = None

    def attr(self, key: str) -> float:
        return float(self.attributes[key])

    def trait(self, key: str) -> float:
        return float(self.personality[key])

    @property
    def height_score(self) -> float:
        """Height mapped to 0-100 (160cm -> 0, ~193cm -> 100)."""
        return max(0.0, min(100.0, (self.height_cm - 160) * 3.0))


@dataclass(frozen=True)
class Team:
    name: str
    player: PlayerProfile
    formation: str = "4-3-3"

    def __post_init__(self) -> None:
        if self.formation not in FORMATIONS:
            raise ValueError(
                f"Unknown formation {self.formation!r}; pick one of {sorted(FORMATIONS)}"
            )

    def line(self, name: str) -> tuple[str, ...]:
        return FORMATIONS[self.formation][name]

    def line_count(self, name: str) -> int:
        return len(self.line(name))
