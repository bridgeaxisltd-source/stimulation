"""Loads and validates player profiles from JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ATTRIBUTE_KEYS, PERSONALITY_KEYS, PlayerProfile

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "players.json"


class PlayerDataError(ValueError):
    pass


def _check_block(player_id: str, block_name: str, block: dict, keys: tuple[str, ...]) -> None:
    missing = [k for k in keys if k not in block]
    if missing:
        raise PlayerDataError(f"{player_id}: {block_name} missing {missing}")
    for key in keys:
        value = block[key]
        if not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise PlayerDataError(f"{player_id}: {block_name}.{key}={value!r} must be 0-100")


def parse_player(raw: dict) -> PlayerProfile:
    player_id = raw.get("id", "<unknown>")
    _check_block(player_id, "attributes", raw.get("attributes", {}), ATTRIBUTE_KEYS)
    _check_block(player_id, "personality", raw.get("personality", {}), PERSONALITY_KEYS)
    return PlayerProfile(
        id=player_id,
        name=raw["name"],
        era=raw.get("era", ""),
        height_cm=int(raw["height_cm"]),
        attributes={k: raw["attributes"][k] for k in ATTRIBUTE_KEYS},
        personality={k: raw["personality"][k] for k in PERSONALITY_KEYS},
        reference=raw.get("reference"),
    )


def load_players(path: str | Path = DEFAULT_DATA_PATH) -> dict[str, PlayerProfile]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    players = [parse_player(p) for p in data["players"]]
    return {p.id: p for p in players}
