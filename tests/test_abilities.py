"""The ability table, checked against the Datasworn asset data."""

import pytest

from ironsworn_tui.abilities import ABILITIES, AssetMove, Boost, Reminder
from ironsworn_tui.rules.datasworn import AssetControlOption, AssetOptionRoll, StatOption, datasworn

# Moves a boost names that its ability's Datasworn enhancements don't list. Each is in the
# ability's text; the data leaves it out.
EXTRA_MOVES: dict[tuple[str, int], set[str]] = {
    # "You may then Secure an Advantage or Face Danger +essence."
    ("invoke", 1): {"secure_an_advantage", "face_danger"},
    # "When you Undertake a Journey to return ... When you Reach Your Destination ..."
    ("tether", 1): {"reach_your_destination"},
    # "When you Turn the Tide, you may Strike with all the fury ..."
    ("thunder_bringer", 3): {"strike"},
    # "When you Turn the Tide ... and your next move is a Strike ..."
    ("weaponmaster", 3): {"strike"},
    # "When your mammoth travels with you as you Undertake a Journey ..."
    ("mammoth", 1): {"undertake_a_journey"},
    # "When you Endure Stress +heart, take +1 momentum on a strong hit."
    ("battle_scarred", 2): {"endure_stress"},
    # The warband abilities: Face Danger, Secure an Advantage, Compel, Battle, Gather
    # Information, and Resupply.
    ("commander", 3): {
        "face_danger",
        "secure_an_advantage",
        "compel",
        "battle",
        "gather_information",
        "resupply",
    },
    # "... you may roll +shadow ... and reroll any dice as you Swear an Iron Vow. When you
    # Fulfill Your Vow on that quest ..."
    ("shadow_kin", 3): {"swear_an_iron_vow", "fulfill_your_vow"},
    # "... when you successfully Fulfill Your Vow (formidable or greater) in service to the
    # spirit ..."
    ("spirit_bound", 3): {"fulfill_your_vow"},
    # "When you Face Danger, Secure an Advantage, or Compel by lying, bluffing, ..."
    ("trickster", 1): {"face_danger", "secure_an_advantage", "compel"},
    # "... to Undertake a Journey using +shadow (instead of +wits)."
    ("shadow_walk", 2): {"undertake_a_journey"},
}


def _boosts(key: tuple[str, int]) -> tuple[Boost, ...]:
    entry = ABILITIES[key]
    if isinstance(entry, AssetMove):
        return entry.boosts
    if isinstance(entry, Reminder):
        return ()
    return entry


def test_every_ability_has_an_entry():
    data = datasworn()
    expected = {(asset.id, n) for asset in data.assets.values() for n in (1, 2, 3)}
    assert set(ABILITIES) == expected


def test_asset_moves_match_the_data():
    data = datasworn()
    for (asset_id, number), entry in ABILITIES.items():
        moves = [move.id for move in data.asset(asset_id).abilities[number - 1].moves]
        if isinstance(entry, AssetMove):
            assert moves == [entry.move], (asset_id, number)
        else:
            assert moves == [], (asset_id, number)


def test_boosts_name_real_moves():
    data = datasworn()
    known = set(data.moves) | set(data.asset_moves)
    for key in ABILITIES:
        for boost in _boosts(key):
            assert set(boost.moves or ()) <= known, (key, boost.label)


def test_boost_moves_are_the_ones_the_data_enhances():
    data = datasworn()
    for key in ABILITIES:
        asset_id, number = key
        enhanced: set[str] = set()
        any_move = False
        for enhancement in data.asset(asset_id).abilities[number - 1].enhancements:
            if enhancement.moves is None or "*" in enhancement.moves:
                any_move = True
            else:
                enhanced |= set(enhancement.moves)
        allowed = enhanced | EXTRA_MOVES.get(key, set())
        for boost in _boosts(key):
            if boost.moves is not None and not any_move:
                assert set(boost.moves) <= allowed, (key, boost.label, enhanced)


def test_boost_stats_are_the_ones_the_data_offers():
    data = datasworn()
    for key in ABILITIES:
        asset_id, number = key
        offered = set[str]()
        for enhancement in data.asset(asset_id).abilities[number - 1].enhancements:
            for option in enhancement.roll_options:
                if isinstance(option, StatOption):
                    offered.add(option.stat)
                elif isinstance(option, AssetControlOption):
                    offered.add(f"meter:{option.control}")
                elif isinstance(option, AssetOptionRoll):
                    offered.add(f"field:{option.option}")
                else:
                    offered.add(f"condition:{option.condition_meter}")
        rolled = set[str]()
        for boost in _boosts(key):
            if boost.roll is not None:
                kind, name = boost.roll.kind, boost.roll.name
                rolled.add(name if kind == "stat" else f"{kind}:{name}")
        assert rolled <= offered | _ROLL_EXCEPTIONS.get(key, set()), (key, rolled, offered)


# Stats a boost rolls that the data doesn't list for the ability. Each is in the text.
_ROLL_EXCEPTIONS: dict[tuple[str, int], set[str]] = {
    # "When you Face Danger +edge in a fight by nimbly avoiding your foe's attacks ..."
    ("dancer", 2): {"edge"},
    # "... Undertake a Journey using +shadow (instead of +wits)."
    ("shadow_walk", 2): {"shadow"},
}


@pytest.mark.parametrize(
    "key",
    [key for key, entry in ABILITIES.items() if isinstance(entry, Reminder)],
)
def test_reminders_say_why(key: tuple[str, int]):
    entry = ABILITIES[key]
    assert isinstance(entry, Reminder)
    assert entry.why.endswith(".")
