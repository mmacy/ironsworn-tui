"""Descriptions for the `move` question's options."""

import pytest

from ironsworn_tui.criteria import CriteriaStyle, move_criteria
from ironsworn_tui.moves import ATTACK, CANNOT_TELL, NO_MOVE, Context, context_options
from ironsworn_tui.rules.datasworn import datasworn


@pytest.mark.parametrize("style", list(CriteriaStyle))
@pytest.mark.parametrize("context", list(Context))
def test_every_option_has_a_description(style: CriteriaStyle, context: Context):
    criteria = move_criteria(datasworn(), context, style)
    assert tuple(criteria) == context_options(context)
    assert all(text.strip() for text in criteria.values())


@pytest.mark.parametrize("context", list(Context))
def test_descriptions_are_unique(context: Context):
    for style in CriteriaStyle:
        criteria = move_criteria(datasworn(), context, style)
        assert len(set(criteria.values())) == len(criteria)


def test_trigger_style_uses_datasworn_trigger_text():
    criteria = move_criteria(datasworn(), Context.EXPLORING, CriteriaStyle.TRIGGER)
    assert criteria["face_danger"] == (
        "When you attempt something risky or react to an imminent threat..."
    )


@pytest.mark.parametrize("context", list(Context))
def test_guide_style_is_one_short_line(context: Context):
    criteria = move_criteria(datasworn(), context, CriteriaStyle.GUIDE)
    assert max(len(text) for text in criteria.values()) <= 140
    assert all("\n" not in text for text in criteria.values())


def test_special_options_read_the_same_in_both_styles():
    guide = move_criteria(datasworn(), Context.FIGHT, CriteriaStyle.GUIDE)
    trigger = move_criteria(datasworn(), Context.FIGHT, CriteriaStyle.TRIGGER)
    assert guide[NO_MOVE] == trigger[NO_MOVE]
    assert guide[CANNOT_TELL] == trigger[CANNOT_TELL]
    assert ATTACK in trigger
