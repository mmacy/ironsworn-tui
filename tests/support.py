"""Shared test helpers: fixed dice, a fixture decider, and a ready engine."""

import random
from pathlib import Path
from typing import Any

from ironsworn_tui.campaign import Character, create_character, new_campaign
from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import Decision, JsonObject, parse_decision
from ironsworn_tui.policy import Thresholds
from ironsworn_tui.rules.datasworn import Stat, datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import TurnEngine

THRESHOLDS = Thresholds(act=0.7, confirm=0.4)
STATS: dict[Stat, int] = {"edge": 2, "heart": 2, "iron": 1, "shadow": 1, "wits": 3}


class Dice(random.Random):
    """Returns the queued rolls in order, and fails if a roll is out of range or missing."""

    def __init__(self) -> None:
        super().__init__()
        self.queue: list[int] = []

    def load(self, *rolls: int) -> None:
        self.queue.extend(rolls)

    def randint(self, a: int, b: int) -> int:
        assert self.queue, f"no roll queued for 1d{b}"
        roll = self.queue.pop(0)
        assert a <= roll <= b, f"{roll} isn't on 1d{b}"
        return roll


class FixtureDecider:
    """Answers every request with the queued move and stat, at the queued confidence."""

    def __init__(self) -> None:
        self.answers: list[tuple[str, str | None, float]] = []
        self.requests: list[JsonObject] = []

    def decide(self, request: JsonObject, target: str) -> Decision:
        self.requests.append(request)
        move, stat, top = self.answers.pop(0)
        answers: dict[str, Any] = {"move": _choice(request["questions"]["move"], move, top)}
        if stat is not None:
            question = f"stat_{move}"
            answers[question] = _choice(request["questions"][question], stat, 0.9)
        response: JsonObject = {
            "request": request,
            "results": [
                {
                    "target": target,
                    "ok": True,
                    "latency_ms": 400.0,
                    "warnings": [],
                    "error": None,
                    "answers": answers,
                }
            ],
        }
        return parse_decision(response, target)


def _choice(question: dict[str, Any], choice: str, top: float) -> dict[str, Any]:
    options = list(question["criteria"])
    rest = (1 - top) / (len(options) - 1)
    probabilities = {option: top if option == choice else rest for option in options}
    n = len(options)
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": probabilities,
        "confidence": (top - 1 / n) / (1 - 1 / n),
    }


def kira() -> Character:
    return create_character(datasworn(), "Kira", "a hunter", STATS, ["archer", "hawk:2", "wright"])


def engine(tmp_path: Path) -> tuple[TurnEngine, Dice, FixtureDecider]:
    dice = Dice()
    decider = FixtureDecider()
    campaign = new_campaign(kira(), "Avenge my village", Rank.EPIC)
    turn = TurnEngine(
        campaign,
        datasworn(),
        dice,
        THRESHOLDS,
        decider=decider,
        path=tmp_path / "kira.json",
        style=CriteriaStyle.GUIDE,
    )
    return turn, dice, decider
