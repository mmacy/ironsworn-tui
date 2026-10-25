"""The command registry: completion, help, and the errors that point to help."""

from pathlib import Path

import pytest

from ironsworn_tui.campaign import Lasting
from ironsworn_tui.commands import ORACLES, REGISTRY, run_command
from ironsworn_tui.registry import CommandError, Completion, filter_options, ghost_pieces
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.rules.progress import Rank
from ironsworn_tui.turn import MoveInputs, TurnEngine
from tests.support import engine


def options(turn: TurnEngine, text: str) -> tuple[str, ...]:
    completion = REGISTRY.complete(turn, text)
    assert completion is not None
    return completion.options


def test_filtering_puts_prefix_matches_before_substring_matches():
    names = ("place-descriptor", "region", "descriptor", "ironlander-name")
    assert filter_options(names, "de") == ("descriptor", "place-descriptor", "ironlander-name")
    assert filter_options(names, "DESC") == ("descriptor", "place-descriptor")
    assert filter_options(names, "") == names


def test_only_a_slash_starts_completion(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert REGISTRY.complete(turn, "I draw my bow") is None
    assert REGISTRY.complete(turn, "") is None


def test_a_slash_offers_every_command(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    offered = options(turn, "/")
    assert set(offered) == {command.name for command in REGISTRY.commands}
    assert options(turn, "/as") == ("ask", "asset")


def test_oracle_offers_its_tables(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    offered = options(turn, "/oracle ")
    assert offered[:2] == ("action", "theme")
    assert offered[-1] == "help"
    assert set(offered) == {*ORACLES, "help"}
    assert options(turn, "/oracle ACT") == ("action", "combat-action")


def test_every_oracle_name_rolls_a_real_table():
    data = datasworn()
    for entry in ORACLES.values():
        assert all(table in data.oracles for table in entry.tables), entry.name


def test_ask_offers_the_likelihoods(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert options(turn, "/ask ") == (
        "almost certain",
        "likely",
        "50/50",
        "unlikely",
        "small chance",
        "help",
    )
    assert options(turn, "/ask sm") == ("small chance",)


def test_completion_takes_names_with_spaces(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    completion = REGISTRY.complete(turn, "/vow mark avenge my")
    assert completion is not None
    assert completion.options == ("Avenge my village",)
    assert completion.apply(0) == "/vow mark Avenge my village"
    assert options(turn, "/ask almost certain Do I") == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/vow ", ("swear", "mark", "fulfill", "forsake", "help")),
        ("/vow swear ", ("troublesome", "dangerous", "formidable", "extreme", "epic", "help")),
        ("/endure ", ("harm", "stress", "help")),
        ("/adjust wounded ", ("mark", "clear", "help")),
        ("/asset upgrade archer ", ("2", "3")),
        ("/asset meter hawk ", ("health",)),
        ("/asset set wright ", ("specialty",)),
        ("/asset debility hawk ", ("on", "off")),
        ("/asset harm ", ("hawk", "help")),
        ("/tide ", ("off", "help")),
        ("/help ", tuple(command.name for command in REGISTRY.commands)),
    ],
)
def test_completion_offers_what_fits_the_position(
    tmp_path: Path, text: str, expected: tuple[str, ...]
):
    turn, _, _ = engine(tmp_path)
    assert options(turn, text) == expected


def test_adjust_offers_meters_debilities_and_tracks(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    offered = options(turn, "/adjust ")
    assert {"health", "spirit", "supply", "momentum", "wounded", "vow", "fight"} <= set(offered)
    assert options(turn, "/adjust vow ") == ("Avenge my village", "help")


def test_completion_offers_foes_and_lasting_effects(tmp_path: Path):
    turn, dice, _ = engine(tmp_path)
    dice.load(6, 1, 1)
    foes = (("Raider", Rank.DANGEROUS), ("Archer", Rank.TROUBLESOME))
    turn.make_move("enter_the_fray", stat="heart", inputs=MoveInputs(foes=foes))
    turn.resolve()
    turn.campaign.lasting.append(Lasting(kind="talisman_2"))
    assert options(turn, "/target ") == ("Raider", "Archer", "help")
    assert options(turn, "/effects end ") == ("1", "help")


def test_a_free_text_argument_shows_a_placeholder(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    completion = REGISTRY.complete(turn, "/scene ")
    assert completion is not None
    assert completion.placeholder == "<text>"
    assert completion.options == ("help",)
    swear = REGISTRY.complete(turn, "/vow swear dangerous ")
    assert swear is not None
    assert (swear.placeholder, swear.options) == ("<vow>", ())


def test_applying_adds_a_space_only_when_more_follows(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert _apply(turn, "/ora") == "/oracle "
    assert _apply(turn, "/vow sw") == "/vow swear "
    assert _apply(turn, "/mo") == "/moves"


def _apply(turn: TurnEngine, text: str) -> str:
    completion = REGISTRY.complete(turn, text)
    assert isinstance(completion, Completion)
    return completion.apply(0)


def test_the_ghost_shows_a_window_around_the_selection():
    names = [f"table{n}" for n in range(50)]
    text = "".join(piece for piece, _ in ghost_pieces(names, 0, 60))
    assert text.startswith("[table0 | table1")
    assert text.endswith("more]")
    assert len(text) <= 60
    middle = ghost_pieces(names, 25, 60)
    assert ("table25", True) in middle
    assert middle[1][0].startswith("+")
    assert ghost_pieces(["a", "b"], 1, 60) == (
        ("[", False),
        ("a", False),
        (" | ", False),
        ("b", True),
        ("]", False),
    )


def test_help_lists_every_command(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    lines = run_command(turn, "/help").help
    for command in REGISTRY.commands:
        assert any(line.startswith(f"/{command.name}: ") for line in lines), command.name


@pytest.mark.parametrize("name", [command.name for command in REGISTRY.commands])
def test_every_command_has_plain_help(tmp_path: Path, name: str):
    turn, _, _ = engine(tmp_path)
    lines = run_command(turn, f"/{name} help").help
    text = "\n".join(lines)
    assert lines[0].startswith(f"/{name}")
    assert "Usage" in text
    assert "Example" in text
    assert "—" not in text
    assert "what do you do" not in text.lower()


def test_every_subcommand_has_help(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    for command in REGISTRY.commands:
        for sub in command.subcommands:
            lines = run_command(turn, f"/{command.name} {sub.name} help").help
            assert lines[0].startswith(f"/{command.name} {sub.name}")
            assert "—" not in "\n".join(lines)


def test_oracle_help_explains_oracles_and_groups_the_tables(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    text = "\n".join(run_command(turn, "/oracle help").help)
    assert "Spark an idea" in text
    assert "Names" in text
    assert "action" in text
    assert "ironlander-name" in text


def test_ask_help_explains_the_odds(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    text = "\n".join(run_command(turn, "/ask help").help)
    assert "likely" in text
    assert "26" in text
    assert "match" in text


def test_help_for_a_command_matches_the_command_help(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    assert run_command(turn, "/help oracle").help == run_command(turn, "/oracle help").help


def test_help_changes_nothing(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    before = list(turn.campaign.log)
    run_command(turn, "/vow swear help")
    assert turn.campaign.log == before


def test_a_typo_suggests_the_command_and_points_to_help(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError) as raised:
        run_command(turn, "/oracel action")
    message = str(raised.value)
    assert "/oracle" in message
    assert "/help" in message


def test_a_bad_argument_shows_the_usage_and_points_to_help(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError) as raised:
        run_command(turn, "/ask maybe")
    message = str(raised.value)
    assert "Usage: /ask <likelihood>" in message
    assert "/ask help" in message


def test_a_bad_subcommand_shows_the_usage(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError) as raised:
        run_command(turn, "/vow swore dangerous Find him")
    message = str(raised.value)
    assert "swear" in message
    assert "/vow help" in message


def test_names_match_in_any_case(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    run_command(turn, "/vow mark avenge my village")
    assert turn.campaign.vows[0].ticks == 1


def test_ask_and_oracle_take_a_question_after_the_option(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    for text in ("/ask almost certain ", "/oracle action "):
        completion = REGISTRY.complete(turn, text)
        assert completion is not None
        assert (completion.placeholder, completion.options) == ("<question>", ())
    assert _apply(turn, "/ask almost") == "/ask almost certain "
    assert _apply(turn, "/oracle act") == "/oracle action "


def test_note_shows_a_placeholder(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    completion = REGISTRY.complete(turn, "/note ")
    assert completion is not None
    assert completion.placeholder == "<text>"


def test_ask_and_oracle_help_show_the_question_form(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    for name in ("ask", "oracle"):
        text = "\n".join(run_command(turn, f"/{name} help").help)
        assert "Do I know which castle I'm in?" in text


def test_a_missing_argument_lists_its_options(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    with pytest.raises(CommandError) as raised:
        run_command(turn, "/vow swear")
    assert "troublesome, dangerous, formidable, extreme, epic" in str(raised.value)
    with pytest.raises(CommandError) as raised:
        run_command(turn, "/oracle")
    assert "such as action or theme" in str(raised.value)


def test_help_says_how_to_play_and_how_to_quit(tmp_path: Path):
    turn, _, _ = engine(tmp_path)
    text = "\n".join(run_command(turn, "/help").help)
    assert "Type what your character does" in text
    assert "/quit" in text
