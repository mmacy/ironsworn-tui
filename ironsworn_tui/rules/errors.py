"""Exceptions the rules raise."""


class RulesError(ValueError):
    """A value is outside what the rules allow, such as a d6 roll of 7."""


class UnknownIdError(LookupError):
    """No move, oracle, NPC, or asset has the given id."""
