"""Progress tracks, ranks, and progress rolls."""

import random
from dataclasses import dataclass
from enum import IntEnum

from ironsworn_tui.rules.datasworn import Datasworn
from ironsworn_tui.rules.dice import (
    ChallengeDice,
    Hit,
    check_challenge_dice,
    hit_for,
    roll_challenge_dice,
)
from ironsworn_tui.rules.errors import RulesError

TICKS_PER_BOX = 4
TRACK_TICKS = 40
BOND_TICKS = 1


class Rank(IntEnum):
    """The rank of a vow, journey, or foe."""

    TROUBLESOME = 1
    DANGEROUS = 2
    FORMIDABLE = 3
    EXTREME = 4
    EPIC = 5

    @property
    def ticks(self) -> int:
        """The ticks one mark of progress fills on a track of this rank."""
        return {
            Rank.TROUBLESOME: 12,
            Rank.DANGEROUS: 8,
            Rank.FORMIDABLE: 4,
            Rank.EXTREME: 2,
            Rank.EPIC: 1,
        }[self]

    @property
    def harm(self) -> int:
        """The harm a foe of this rank inflicts, equal to the rank's value."""
        return self.value


def npc_rank(data: Datasworn, npc_id: str) -> Rank:
    """Return an NPC's rank from the Datasworn data.

    Args:
        data: The Datasworn data.
        npc_id: The NPC's id, such as `warrior`.

    Returns:
        The rank.

    Raises:
        UnknownIdError: If no NPC has the id.
    """
    return Rank(data.npc(npc_id)["rank"])


@dataclass(frozen=True)
class ProgressRoll:
    """A progress roll: the filled boxes on a track against two d10 challenge dice.

    Progress rolls ignore momentum, and momentum can't be burned on them.

    Attributes:
        ticks: The ticks on the track, 0 to 40.
        challenge_dice: The two d10s.
        hit: The result.
    """

    ticks: int
    challenge_dice: ChallengeDice
    hit: Hit

    @property
    def score(self) -> int:
        """The progress score: the number of fully filled boxes."""
        return self.ticks // TICKS_PER_BOX

    @property
    def match(self) -> bool:
        """True when the challenge dice show the same number."""
        return self.challenge_dice[0] == self.challenge_dice[1]


def evaluate_progress(ticks: int, challenge_dice: ChallengeDice) -> ProgressRoll:
    """Work out a progress roll from challenge dice that are already rolled.

    Args:
        ticks: The ticks on the track, 0 to 40.
        challenge_dice: The two d10 results.

    Returns:
        The roll and its result.

    Raises:
        RulesError: If `ticks` is outside 0 to 40 or a die is out of range.
    """
    if not 0 <= ticks <= TRACK_TICKS:
        raise RulesError(f"ticks must be 0 to {TRACK_TICKS}, got {ticks}")
    check_challenge_dice(challenge_dice)
    return ProgressRoll(
        ticks=ticks,
        challenge_dice=challenge_dice,
        hit=hit_for(ticks // TICKS_PER_BOX, challenge_dice),
    )


def roll_progress(ticks: int, rng: random.Random) -> ProgressRoll:
    """Roll the challenge dice for a progress roll and work out the result."""
    return evaluate_progress(ticks, roll_challenge_dice(rng))
