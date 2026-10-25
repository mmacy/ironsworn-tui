"""The oracles the player can roll: the yes/no likelihoods and the oracle tables by short name.

The decision model reads these too, when it suggests a table or a likelihood for a question
typed after `/oracle`.
"""

from dataclasses import dataclass

from ironsworn_tui.rules.oracles import Likelihood

# The likelihoods by the names `/ask` takes.
LIKELIHOODS = {
    "almost certain": Likelihood.ALMOST_CERTAIN,
    "likely": Likelihood.LIKELY,
    "50/50": Likelihood.FIFTY_FIFTY,
    "unlikely": Likelihood.UNLIKELY,
    "small chance": Likelihood.SMALL_CHANCE,
}
# The `likelihood` question's options, by option id, with the name `/ask` takes for each.
LIKELIHOOD_OPTIONS = {
    "almost_certain": "almost certain",
    "likely": "likely",
    "fifty_fifty": "50/50",
    "unlikely": "unlikely",
    "small_chance": "small chance",
}


@dataclass(frozen=True)
class OracleEntry:
    """An oracle table under a short name.

    Attributes:
        name: The short name `/oracle` takes, such as `action`.
        tables: The table ids. With more than one, a roll picks one of them, as the rulebook
            says for Ironlander names.
        summary: What the table gives, for the help.
    """

    name: str
    tables: tuple[str, ...]
    summary: str


def _entry(name: str, table: str, summary: str) -> OracleEntry:
    return OracleEntry(name, (f"classic/{table}",), summary)


ORACLE_GROUPS: tuple[tuple[str, tuple[OracleEntry, ...]], ...] = (
    (
        "Spark an idea",
        (
            _entry("action", "action_and_theme/action", "a verb, such as Clash or Scheme"),
            _entry("theme", "action_and_theme/theme", "a noun, such as Risk or Ally"),
        ),
    ),
    (
        "Characters",
        (
            _entry("role", "character/role", "who they are, such as Healer"),
            _entry("goal", "character/goal", "what they want, such as Obtain an object"),
            _entry("descriptor", "character/descriptor", "what they're like, such as Stoic"),
        ),
    ),
    (
        "Names",
        (
            OracleEntry(
                "ironlander-name",
                ("classic/name/ironlander/a", "classic/name/ironlander/b"),
                "a name for one of the people of the Ironlands",
            ),
            _entry("elf-name", "name/elf", "a name for an elf"),
            _entry("giant-name", "name/other/giants", "a name for a giant"),
            _entry("varou-name", "name/other/varou", "a name for a varou"),
            _entry("troll-name", "name/other/trolls", "a name for a troll"),
        ),
    ),
    (
        "Places",
        (
            _entry("region", "place/region", "a region of the Ironlands, such as Deep Wilds"),
            _entry("location", "place/location", "a place, such as Ruin or Mine"),
            _entry(
                "coastal-location",
                "place/coastal_waters_location",
                "a place on the water, such as Fleet",
            ),
            _entry("place-descriptor", "place/descriptor", "what a place is like, such as Remote"),
        ),
    ),
    (
        "Settlements",
        (
            _entry(
                "settlement-name",
                "settlement/name",
                "where a settlement's name comes from, with an example",
            ),
            _entry(
                "quick-name-prefix",
                "settlement/quick_name/prefix",
                "the first half of a name, such as Raven",
            ),
            _entry(
                "quick-name-suffix",
                "settlement/quick_name/suffix",
                "the second half of a name, such as ford",
            ),
            _entry(
                "settlement-trouble",
                "settlement/trouble",
                "a settlement's problem, such as Dreadful omens",
            ),
        ),
    ),
    (
        "Turning points",
        (
            _entry(
                "plot-twist",
                "turning_point/major_plot_twist",
                "a surprise, such as A trap is sprung",
            ),
            _entry(
                "combat-action", "turning_point/combat_action", "what a foe does next in a fight"
            ),
            _entry(
                "mystic-backlash",
                "turning_point/mystic_backlash",
                "what goes wrong when a ritual fails",
            ),
            _entry(
                "challenge-rank",
                "turning_point/challenge_rank",
                "how hard a foe or a vow is, from Troublesome to Epic",
            ),
        ),
    ),
    (
        "Fate",
        (
            _entry(
                "pay-the-price",
                "fate/pay_the_price/pay_the_price",
                "a cost or complication, as after a miss",
            ),
        ),
    ),
)
ORACLES = {entry.name: entry for _, entries in ORACLE_GROUPS for entry in entries}
# Only a move rolls these, so the decision model never suggests them.
MOVE_ONLY = ("pay-the-price",)
# The `table` question's options: every table the player rolls, in the order the help lists them.
ASKED_TABLES = tuple(name for name in ORACLES if name not in MOVE_ONLY)
