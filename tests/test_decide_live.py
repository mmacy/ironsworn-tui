"""Live calls to a hosted decision model through jevtester. Run with `uv run pytest -m live`."""

import pytest

from ironsworn_tui.criteria import CriteriaStyle
from ironsworn_tui.decide import TurnState, build_request, jevtester_server
from ironsworn_tui.moves import Context, context_options
from ironsworn_tui.rules.datasworn import datasworn
from ironsworn_tui.settings import load_settings

pytestmark = pytest.mark.live


def test_decision_1_answers_a_turn():
    state = TurnState(
        character="Kira, a hunter",
        situation="Two raiders with spears block the bridge.",
        context=Context.FIGHT,
        initiative="character",
        player_says="I drive my spear at the nearer raider's chest.",
    )
    with jevtester_server(load_settings()) as client:
        decision = client.decide(
            build_request(datasworn(), state, CriteriaStyle.GUIDE), "decision-1@foundry"
        )
    assert decision.ok, decision.error
    assert decision.move is not None
    assert decision.move.choice in context_options(Context.FIGHT)
    assert decision.stat_for("attack") is not None
