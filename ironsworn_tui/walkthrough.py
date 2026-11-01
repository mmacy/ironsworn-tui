"""The character creation walkthrough: a Textual app that asks each setup step in turn.

The steps follow the rulebook's campaign setup (page 202). Each step shows a short rules
line, and the app returns a [`Setup`][ironsworn_tui.creation.Setup] once the player
confirms the review, or None if they quit.
"""

import random
from collections.abc import Callable, Sequence
from typing import ClassVar, get_args

from rich.markup import escape
from rich.table import Table
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ContentSwitcher, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from ironsworn_tui.campaign import STARTING_ASSETS, STARTING_STATS, AssetError
from ironsworn_tui.creation import (
    AssetPick,
    Setup,
    begin_campaign,
    needs_ability,
    pickable_abilities,
    quest_starters,
    roll_name,
    roll_place_name,
    roll_spark,
    roll_truth,
)
from ironsworn_tui.rules.datasworn import Asset, Datasworn, Stat, Truth
from ironsworn_tui.rules.errors import UnknownIdError
from ironsworn_tui.rules.progress import Rank

SECTIONS = (
    "Create your character",
    "Create your world",
    "Mark your background bonds",
    "Write your background vow",
    "Envision your inciting incident",
    "Set the scene",
    "Review",
)
STAT_ORDER: tuple[Stat, ...] = get_args(Stat.__value__)
STAT_TEXT: dict[Stat, str] = {
    "edge": "Quickness, agility, and prowess in ranged combat",
    "heart": "Courage, willpower, empathy, sociability, and loyalty",
    "iron": "Physical strength, endurance, aggressiveness, and prowess in close combat",
    "shadow": "Sneakiness, deceptiveness, and cunning",
    "wits": "Expertise, knowledge, and observation",
}
# The rulebook's order of asset types (page 39).
ASSET_CATEGORIES = ("Companion", "Path", "Combat Talent", "Ritual")
# The rulebook's example character, Saskia, gives each example (pages 193 to 199).
BOND_EXAMPLES = ("Cinderhome", "The clan overseer", "")
LEAVE_OPEN = "Leave it blank, and fill it in as you play"
BACKGROUND_RANKS = (Rank.EXTREME, Rank.EPIC)
VOW_RANKS = (Rank.TROUBLESOME, Rank.DANGEROUS, Rank.FORMIDABLE)
STARTS = (
    ("in_media_res", "In media res: begin as the incident happens, and swear the vow now"),
    ("prologue", "The normal world: begin with a prologue, and swear the vow later"),
)


class Advance(Message):
    """Asks the walkthrough to move on from a control: to the next control, or step."""

    def __init__(self, source: Widget) -> None:
        """Create the message for the control that sent it."""
        super().__init__()
        self.source = source


class ChoiceList(Static, can_focus=True):
    """Picks one of a few options with the arrows or the digit keys. Enter moves on."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
        Binding("enter", "advance", show=False),
    ]
    DEFAULT_CSS = """
    ChoiceList { padding: 0 1; height: auto; }
    ChoiceList:focus { background: $boost; }
    """

    class Changed(Message):
        """The selection changed."""

        def __init__(self, choices: ChoiceList, index: int | None) -> None:
            """Create the message."""
            super().__init__()
            self.choices = choices
            self.index = index

        @property
        def control(self) -> ChoiceList:
            """The list that changed."""
            return self.choices

    def __init__(
        self,
        options: Sequence[str],
        selected: int | None = None,
        *,
        spaced: bool = False,
        unavailable: dict[int, str] | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Create the list.

        Args:
            options: The options' text.
            selected: The option selected at first, or None.
            spaced: True to put a blank line between options, for long ones.
            unavailable: The options that can't be picked, by index, with the reason.
            id: The widget's id.
            classes: The widget's CSS classes.
        """
        super().__init__(id=id, classes=classes)
        self.options = list(options)
        self.selected = selected
        self.spaced = spaced
        self.unavailable = unavailable or {}

    def on_mount(self) -> None:
        """Draw the options."""
        self.draw()

    def on_focus(self) -> None:
        """Redraw to show the selection in the focus style."""
        self.draw()

    def on_blur(self) -> None:
        """Redraw without the focus style."""
        self.draw()

    def draw(self) -> None:
        """Draw each option with its key and a mark for the selected one."""
        grid = Table.grid(padding=(0, 1))
        grid.add_column(no_wrap=True)
        grid.add_column()
        for index, option in enumerate(self.options):
            if self.spaced and index:
                grid.add_row("", "")
            key = str(index + 1) if index < 9 else " "
            if index in self.unavailable:
                text = Text(f"{option} ({self.unavailable[index]})", style="dim")
                grid.add_row(Text(f"{key}  - ", style="dim"), text)
                continue
            chosen = index == self.selected
            text = Text(option, style="bold" if chosen else "")
            grid.add_row(f"{key} {'(•)' if chosen else '( )'}", text)
        self.update(grid)

    def select(self, index: int | None) -> None:
        """Select an option, or none. An unavailable option isn't selected."""
        if index in self.unavailable:
            return
        self.selected = index
        self.draw()
        self.post_message(self.Changed(self, index))

    def action_move(self, step: int) -> None:
        """Select the option above or below."""
        available = [i for i in range(len(self.options)) if i not in self.unavailable]
        if not available:
            return
        if self.selected is None:
            self.select(available[0] if step > 0 else available[-1])
            return
        current = self.selected
        ahead = [index for index in available if (index - current) * step > 0]
        if ahead:
            self.select(min(ahead, key=lambda index: abs(index - current)))

    def action_advance(self) -> None:
        """Move on."""
        self.post_message(Advance(self))

    def on_key(self, event: events.Key) -> None:
        """Select an option by its digit."""
        character = event.character or ""
        if character.isdigit() and 1 <= int(character) <= min(9, len(self.options)):
            self.select(int(character) - 1)
            event.stop()


class StatGrid(Static, can_focus=True):
    """Arranges the bonuses 3, 2, 2, 1, and 1 across the five stats, with the arrows and the
    keys 1 to 3."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
        Binding("enter", "advance", show=False),
    ]
    DEFAULT_CSS = """
    StatGrid { padding: 0 1; height: auto; }
    StatGrid:focus { background: $boost; }
    """

    def __init__(self, values: dict[Stat, int] | None = None) -> None:
        """Create the grid, with any values already given."""
        super().__init__()
        self.values: dict[Stat, int] = dict(values or {})
        self.row = 0

    def on_mount(self) -> None:
        """Draw the stats."""
        self.draw()

    def left(self) -> list[int]:
        """The bonuses still to set, highest first."""
        left: list[int] = list(STARTING_STATS)
        for value in self.values.values():
            left.remove(value)
        return left

    def draw(self) -> None:
        """Draw each stat with its bonus and what it covers, and the bonuses still to set."""
        grid = Table.grid(padding=(0, 1))
        grid.add_column(no_wrap=True)
        grid.add_column(no_wrap=True)
        grid.add_column(no_wrap=True)
        grid.add_column()
        for index, stat in enumerate(STAT_ORDER):
            here = index == self.row
            value = self.values.get(stat)
            grid.add_row(
                ">" if here else " ",
                Text(stat.capitalize(), style="bold" if here else ""),
                str(value) if value is not None else "-",
                Text(STAT_TEXT[stat], style="dim"),
            )
        left = self.left()
        footer = "Bonuses left: " + ", ".join(map(str, left)) if left else "All five stats are set."
        table = Table.grid()
        table.add_row(grid)
        table.add_row("")
        table.add_row(footer)
        self.update(table)

    def action_move(self, step: int) -> None:
        """Move to the stat above or below."""
        self.row = max(0, min(len(STAT_ORDER) - 1, self.row + step))
        self.draw()

    def action_advance(self) -> None:
        """Move on."""
        self.post_message(Advance(self))

    def set_bonus(self, value: int) -> None:
        """Set the current stat's bonus, taking it from another stat if none is left."""
        stat = STAT_ORDER[self.row]
        self.values.pop(stat, None)
        if value not in self.left():
            for other in STAT_ORDER:
                if self.values.get(other) == value:
                    del self.values[other]
                    break
        self.values[stat] = value
        self.draw()

    def on_key(self, event: events.Key) -> None:
        """Set a bonus with 1, 2, or 3."""
        if event.character in ("1", "2", "3"):
            self.set_bonus(int(event.character))
            event.stop()


class AssetList(OptionList):
    """The assets by type. Space picks or drops the highlighted one, and Enter moves on."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "pick", show=False),
        Binding("enter", "advance", show=False),
    ]

    class Toggled(Message):
        """The player picked or dropped an asset."""

        def __init__(self, asset_id: str) -> None:
            """Create the message."""
            super().__init__()
            self.asset_id = asset_id

    def action_pick(self) -> None:
        """Pick or drop the highlighted asset."""
        if self.highlighted is None:
            return
        option = self.get_option_at_index(self.highlighted)
        if option.id is not None:
            self.post_message(self.Toggled(option.id))

    def action_advance(self) -> None:
        """Move on."""
        self.post_message(Advance(self))


class Step(VerticalScroll):
    """One step of the walkthrough.

    Attributes:
        section: The rulebook step it belongs to, one of `SECTIONS`.
        title: Its name in the heading.
        rules: The rules line.
        keys: The keys it adds to the hint, such as `Ctrl+R roll a name`.
        walkthrough: The walkthrough the step is part of.
    """

    DEFAULT_CSS = """
    Step { height: 1fr; }
    Step > Label { margin-top: 1; }
    Step .detail { margin: 1 0 0 0; color: $text-muted; }
    """

    section: str = ""
    title: str = ""
    rules: str = ""
    keys: str = ""
    walkthrough: Walkthrough

    def skipped(self, setup: Setup) -> bool:
        """True when the step has nothing to ask, as the asset details step for archer."""
        return False

    def enter(self, setup: Setup) -> None:
        """Bring the step up to date with the answers so far, before it's shown."""

    def check(self) -> str | None:
        """Return what's missing or wrong, or None when the step is done."""
        return None

    def apply(self, setup: Setup) -> None:
        """Write the step's answers into the setup."""


class NameStep(Step):
    """The character's name and description."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("ctrl+r", "roll", show=False)]
    section = SECTIONS[0]
    title = "Name"
    rules = (
        "Envision your character, considering their motivations, skills, background, "
        "appearance, personality, and connections to the world. Give your character a name, "
        "and a few words that sum them up. The decision model reads both."
    )
    keys = "Ctrl+R roll an Ironlander name"

    def __init__(self, name: str, taken: Callable[[str], bool]) -> None:
        """Create the step, with a name to start from and a check for names in use."""
        super().__init__()
        self.start_name = name
        self.taken = taken

    def compose(self) -> ComposeResult:
        """Lay out the two inputs."""
        yield Label("Name")
        yield Input(value=self.start_name, placeholder="Saskia", id="name")
        yield Label("Description")
        yield Input(placeholder="a former raider turned farmer", id="description")

    def action_roll(self) -> None:
        """Roll an Ironlander name into the name input."""
        name = roll_name(self.walkthrough.data, self.walkthrough.rng)
        self.query_one("#name", Input).value = name

    def _value(self, input_id: str) -> str:
        return self.query_one(f"#{input_id}", Input).value.strip()

    def check(self) -> str | None:
        """Need a name that can name a file and isn't in use, and a description."""
        name = self._value("name")
        if not name:
            return "Give your character a name."
        if any(character in name for character in "/\\") or name.startswith("."):
            return "A name can't have / or \\ in it, or start with a dot."
        if self.taken(name):
            return f"A campaign named {name} already exists. Choose another name."
        if not self._value("description"):
            return "Write a few words about your character."
        return None

    def apply(self, setup: Setup) -> None:
        """Set the name and description."""
        setup.name = self._value("name")
        setup.description = self._value("description")


class StatsStep(Step):
    """The five stats."""

    section = SECTIONS[0]
    title = "Stats"
    rules = (
        "Set your stats by arranging the bonuses 3, 2, 2, 1, and 1 across them in any order. "
        "A move adds one stat to the action die, so put the 3 where your character is "
        "strongest."
    )
    keys = "Up and down choose a stat · 1-3 set its bonus"

    def compose(self) -> ComposeResult:
        """Lay out the grid."""
        yield StatGrid()

    def check(self) -> str | None:
        """Need all five stats."""
        left = self.query_one(StatGrid).left()
        if left:
            return "Set every stat. Bonuses left: " + ", ".join(map(str, left)) + "."
        return None

    def apply(self, setup: Setup) -> None:
        """Set the stats."""
        setup.stats = dict(self.query_one(StatGrid).values)


def asset_detail(asset: Asset) -> Text:
    """Describe an asset for the picker: its type, requirement, and abilities."""
    text = Text()
    text.append(asset.name, style="bold")
    text.append(f" ({asset.category.lower()})\n")
    if asset.requirement:
        text.append(" ".join(asset.requirement.split()) + "\n")
    for number, ability in enumerate(asset.abilities, 1):
        mark = "[x]" if ability.enabled else "[ ]"
        body = " ".join(ability.text.split())
        if ability.name:
            body = f"{ability.name}: {body}"
        text.append(f"\n{mark} {number}. {body}\n")
    if not any(ability.enabled for ability in asset.abilities):
        text.append("\nYou choose its starting ability.", style="italic")
    return text


class AssetsStep(Step):
    """The three starting assets."""

    DEFAULT_CSS = """
    AssetsStep Horizontal { height: 1fr; }
    AssetsStep AssetList { width: 36; height: 100%; }
    AssetsStep #asset-detail { width: 1fr; height: 100%; padding: 0 1; }
    """
    section = SECTIONS[0]
    title = "Assets"
    rules = (
        "Pick three assets from companions, paths, combat talents, and rituals. All assets "
        "include three abilities, and most have a default ability filled in. If an asset "
        "doesn't have a starting ability, you choose one."
    )
    keys = "Up and down browse · Space pick or drop"

    def __init__(self, data: Datasworn) -> None:
        """Create the step."""
        super().__init__()
        self.data = data
        self.picked: list[str] = []

    def compose(self) -> ComposeResult:
        """Lay out the picked line, the asset list, and the highlighted asset."""
        yield Static(self._picked_text(), id="picked")
        with Horizontal():
            yield AssetList(*self._options())
            with VerticalScroll(id="asset-detail"):
                yield Static(id="asset-text")

    def _options(self) -> list[Option | None]:
        options: list[Option | None] = []
        for category in ASSET_CATEGORIES:
            if options:
                options.append(None)
            options.append(Option(Text(category + "s", style="bold"), disabled=True))
            options += [
                Option(self._prompt(asset), id=asset.id)
                for asset in self.data.assets.values()
                if asset.category == category
            ]
        return options

    def _prompt(self, asset: Asset) -> Text:
        return Text(f"{'[x]' if asset.id in self.picked else '[ ]'} {asset.name}")

    def _picked_text(self) -> str:
        names = [self.data.asset(asset_id).name for asset_id in self.picked]
        return f"Picked {len(names)} of {STARTING_ASSETS}: {', '.join(names) or 'none yet'}"

    def on_mount(self) -> None:
        """Highlight the first asset."""
        assets = self.query_one(AssetList)
        assets.highlighted = 1

    @on(OptionList.OptionHighlighted)
    def show_asset(self, event: OptionList.OptionHighlighted) -> None:
        """Describe the highlighted asset."""
        if event.option.id is not None:
            text = asset_detail(self.data.asset(event.option.id))
            self.query_one("#asset-text", Static).update(text)

    @on(AssetList.Toggled)
    def toggle(self, event: AssetList.Toggled) -> None:
        """Pick or drop an asset."""
        if event.asset_id in self.picked:
            self.picked.remove(event.asset_id)
        elif len(self.picked) == STARTING_ASSETS:
            self.walkthrough.show_error(f"You have {STARTING_ASSETS} assets. Drop one first.")
            return
        else:
            self.picked.append(event.asset_id)
        self.walkthrough.show_error("")
        assets = self.query_one(AssetList)
        index = assets.get_option_index(event.asset_id)
        assets.replace_option_prompt_at_index(index, self._prompt(self.data.asset(event.asset_id)))
        self.query_one("#picked", Static).update(self._picked_text())

    def check(self) -> str | None:
        """Need three assets."""
        if len(self.picked) != STARTING_ASSETS:
            return f"Pick {STARTING_ASSETS} assets. You have {len(self.picked)}."
        return None

    def apply(self, setup: Setup) -> None:
        """Set the assets, keeping the details of any already set."""
        kept = {pick.id: pick for pick in setup.assets}
        setup.assets = [kept.get(asset_id, AssetPick(asset_id)) for asset_id in self.picked]


def _needs_details(data: Datasworn, asset_id: str) -> bool:
    asset = data.asset(asset_id)
    return needs_ability(data, asset_id) or bool(asset.texts) or bool(asset.selects)


class AssetDetailsStep(Step):
    """The starting ability and fields of each asset that needs them, such as a companion."""

    section = SECTIONS[0]
    title = "Asset details"
    rules = (
        "Choose a starting ability for each asset that doesn't have one. Give your companions "
        "a name, and fill in what your other assets ask for."
    )
    keys = "Tab next field · Up and down or 1-9 choose"

    def __init__(self, data: Datasworn) -> None:
        """Create the step."""
        super().__init__()
        self.data = data
        self.built: list[str] = []
        self.abilities: dict[str, tuple[ChoiceList, tuple[int, ...]]] = {}
        self.selects: dict[tuple[str, str], tuple[ChoiceList, tuple[str, ...]]] = {}
        self.texts: dict[tuple[str, str], Input] = {}

    def skipped(self, setup: Setup) -> bool:
        """Skip the step when no picked asset needs details."""
        return not any(_needs_details(self.data, pick.id) for pick in setup.assets)

    def enter(self, setup: Setup) -> None:
        """Lay out the questions for the picked assets, when they changed."""
        ids = [pick.id for pick in setup.assets if _needs_details(self.data, pick.id)]
        if ids == self.built:
            return
        self.built = ids
        self.remove_children()
        self.abilities.clear()
        self.selects.clear()
        self.texts.clear()
        picks = {pick.id: pick for pick in setup.assets}
        widgets: list[Widget] = []
        for asset_id in ids:
            asset = self.data.asset(asset_id)
            pick = picks[asset_id]
            widgets.append(Label(f"[b]{escape(asset.name)}[/b]"))
            if needs_ability(self.data, asset_id):
                pickable = pickable_abilities(self.data, asset_id)
                options = [" ".join(ability.text.split()) for ability in asset.abilities]
                unavailable = {
                    number - 1: "upgrade to it in play, because it changes your stats"
                    for number in range(1, len(options) + 1)
                    if number not in pickable
                }
                selected = pick.ability - 1 if pick.ability in pickable else None
                choices = ChoiceList(options, selected, spaced=True, unavailable=unavailable)
                self.abilities[asset_id] = (choices, tuple(range(1, len(options) + 1)))
                widgets += [Label("Starting ability"), choices]
            for field, select in asset.selects.items():
                ids_ = tuple(select.choices)
                labels = [choice.label.capitalize() for choice in select.choices.values()]
                value = pick.fields.get(field)
                choices = ChoiceList(labels, ids_.index(value) if value in ids_ else None)
                self.selects[asset_id, field] = (choices, ids_)
                widgets += [Label(select.label.capitalize()), choices]
            for field, label in asset.texts.items():
                text = Input(value=pick.fields.get(field, ""))
                self.texts[asset_id, field] = text
                widgets += [Label(f"{label.capitalize()} (optional)"), text]
        self.mount_all(widgets)

    def check(self) -> str | None:
        """Need each starting ability and each select field."""
        for asset_id, (choices, _) in self.abilities.items():
            if choices.selected is None:
                return f"Choose {self.data.asset(asset_id).name}'s starting ability."
        for (asset_id, field), (choices, _) in self.selects.items():
            if choices.selected is None:
                return f"Choose {self.data.asset(asset_id).name}'s {field}."
        return None

    def apply(self, setup: Setup) -> None:
        """Set each asset's ability and fields."""
        for pick in setup.assets:
            if pick.id in self.abilities:
                choices, numbers = self.abilities[pick.id]
                pick.ability = numbers[choices.selected] if choices.selected is not None else None
            fields: dict[str, str] = {}
            for (asset_id, field), (choices, ids) in self.selects.items():
                if asset_id == pick.id and choices.selected is not None:
                    fields[field] = ids[choices.selected]
            for (asset_id, field), text in self.texts.items():
                if asset_id == pick.id and text.value.strip():
                    fields[field] = text.value.strip()
            pick.fields = fields


class EquipmentStep(Step):
    """Whether the character carries a deadly weapon."""

    section = SECTIONS[0]
    title = "Equipment"
    rules = (
        "Make note of any important equipment or items you start with. If you are armed "
        "with a deadly weapon, such as a sword, axe, spear, or bow, you inflict 2 harm. If "
        "you are unarmed or using a simple weapon, such as a shield, staff, or club, you "
        "inflict 1 harm."
    )
    keys = "Up and down or 1-2 choose"

    def compose(self) -> ComposeResult:
        """Lay out the choice."""
        yield ChoiceList(
            ["Armed with a deadly weapon: 2 harm", "Unarmed, or a simple weapon: 1 harm"], 0
        )

    def apply(self, setup: Setup) -> None:
        """Set the harm."""
        setup.harm = 2 if self.query_one(ChoiceList).selected == 0 else 1


class TruthStep(Step):
    """One world truth."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "roll", show=False),
        Binding("a", "roll_rest", show=False),
    ]
    section = SECTIONS[1]
    rules = (
        "Choose one of the three options and make it true for your version of the "
        "Ironlands, roll for it, or leave it blank. Keep an eye out for quest starters which "
        "trigger an idea for a background vow or an inciting incident."
    )
    keys = "1-4 choose · r roll · a roll this and the rest"

    def __init__(self, truth: Truth, number: int, count: int) -> None:
        """Create the step for a truth, the `number`th of `count`."""
        super().__init__()
        self.truth = truth
        self.title = f"{truth.name} ({number} of {count})"

    def compose(self) -> ComposeResult:
        """Lay out the options and the quest starter."""
        options = [option.description for option in self.truth.options] + [LEAVE_OPEN]
        yield ChoiceList(options, spaced=True)
        yield Static("", classes="detail", id="starter")

    @on(ChoiceList.Changed)
    def show_starter(self, event: ChoiceList.Changed) -> None:
        """Show the selected option's quest starter."""
        index = event.index
        text = ""
        if index is not None and index < len(self.truth.options):
            text = "Quest starter: " + self.truth.options[index].quest_starter
        self.query_one("#starter", Static).update(text)

    def roll(self) -> None:
        """Roll 1 to 100 and select the option it picks."""
        roll, index = roll_truth(self.walkthrough.data, self.truth.id, self.walkthrough.rng)
        self.query_one(ChoiceList).select(index)
        self.walkthrough.show_error(f"Rolled {roll}.")

    def action_roll(self) -> None:
        """Roll for this truth."""
        self.roll()

    def action_roll_rest(self) -> None:
        """Roll for this truth and every one after it, then move past them."""
        self.walkthrough.roll_rest(self)

    def check(self) -> str | None:
        """Need a choice."""
        if self.query_one(ChoiceList).selected is None:
            return "Choose an option, roll, or leave it blank."
        return None

    def apply(self, setup: Setup) -> None:
        """Set the truth, or leave it out when it's left open."""
        selected = self.query_one(ChoiceList).selected
        if selected is not None and selected < len(self.truth.options):
            setup.truths[self.truth.id] = selected
        else:
            setup.truths.pop(self.truth.id, None)


class PlaceStep(Step):
    """The region and place where the story begins."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("ctrl+r", "roll", show=False)]
    section = SECTIONS[1]
    title = "Where your story begins"
    rules = (
        "Choose where your story begins: a region of the Ironlands, and a place in it. Is "
        "your character part of a community, or wandering the wilderness?"
    )
    keys = "1-9 choose a region · Tab place · Ctrl+R roll a settlement name"

    def __init__(self, data: Datasworn) -> None:
        """Create the step."""
        super().__init__()
        self.data = data
        self.region_ids = tuple(data.regions)

    def compose(self) -> ComposeResult:
        """Lay out the regions, the highlighted region, and the place."""
        yield ChoiceList([region.name for region in self.data.regions.values()])
        yield Static("", classes="detail", id="region")
        yield Label("Place (optional)")
        yield Input(placeholder="Cinderhome", id="place")

    @on(ChoiceList.Changed)
    def show_region(self, event: ChoiceList.Changed) -> None:
        """Describe the selected region."""
        if event.index is not None:
            region = self.data.regions[self.region_ids[event.index]]
            text = f"{region.summary}\n\nQuest starter: {region.quest_starter}"
            self.query_one("#region", Static).update(text)

    def action_roll(self) -> None:
        """Roll a settlement name into the place input."""
        name = roll_place_name(self.data, self.walkthrough.rng)
        self.query_one("#place", Input).value = name

    def check(self) -> str | None:
        """Need a region."""
        if self.query_one(ChoiceList).selected is None:
            return "Choose the region where your story begins."
        return None

    def apply(self, setup: Setup) -> None:
        """Set the region and place."""
        selected = self.query_one(ChoiceList).selected
        setup.region = self.region_ids[selected] if selected is not None else None
        setup.place = self.query_one("#place", Input).value.strip()


class BondsStep(Step):
    """Up to three background bonds."""

    section = SECTIONS[2]
    title = "Background bonds"
    rules = (
        "Give yourself up to three bonds, to a community or an individual. Mark a tick on "
        "your bonds track for each. You can hold a bond in reserve and introduce it in play."
    )

    def compose(self) -> ComposeResult:
        """Lay out three inputs."""
        for number in range(1, 4):
            yield Label(f"Bond {number} (optional)")
            yield Input(placeholder=BOND_EXAMPLES[number - 1])

    def apply(self, setup: Setup) -> None:
        """Set the bonds that were written."""
        setup.bonds = [text.value.strip() for text in self.query(Input) if text.value.strip()]


def _starters_text(starters: list[tuple[str, str]]) -> str:
    if not starters:
        return ""
    lines = ["Quest starters from your world:"]
    lines += [f"{source}: {text}" for source, text in starters]
    return "\n\n".join(lines)


class BackgroundVowStep(Step):
    """The background vow and its rank."""

    section = SECTIONS[3]
    title = "Background vow"
    rules = (
        "Your background vow represents a primary motivation or ultimate goal, sworn years "
        "ago or in reaction to a recent, major event. Give it a rank of extreme or epic. You "
        "don't make the Swear an Iron Vow move for it."
    )
    keys = "Tab next field · 1-2 choose the rank"

    def compose(self) -> ComposeResult:
        """Lay out the vow, the rank, and the quest starters."""
        yield Label("Vow")
        yield Input(placeholder="Defeat the Red Moon clan", id="background-vow")
        yield Label("Rank")
        yield ChoiceList([rank.name.capitalize() for rank in BACKGROUND_RANKS], 1)
        yield Static("", classes="detail", id="starters")

    def enter(self, setup: Setup) -> None:
        """Show the quest starters of the world so far."""
        text = _starters_text(quest_starters(self.walkthrough.data, setup))
        self.query_one("#starters", Static).update(text)

    def check(self) -> str | None:
        """Need a vow."""
        if not self.query_one("#background-vow", Input).value.strip():
            return "Write your background vow."
        return None

    def apply(self, setup: Setup) -> None:
        """Set the vow and rank."""
        setup.background_vow = self.query_one("#background-vow", Input).value.strip()
        selected = self.query_one(ChoiceList).selected
        setup.background_rank = BACKGROUND_RANKS[selected if selected is not None else 1]


class IncidentStep(Step):
    """The inciting incident."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("ctrl+r", "roll", show=False)]
    section = SECTIONS[4]
    title = "Inciting incident"
    rules = (
        "Your inciting incident is an imminent threat or compelling need that forces your "
        "character into action. Make it personal, make it a problem that won't go away on "
        "its own, and give it a ticking clock."
    )
    keys = "Ctrl+R roll the action and theme oracles"

    def compose(self) -> ComposeResult:
        """Lay out the incident, the oracle's answer, and the quest starters."""
        yield Label("Inciting incident (optional)")
        yield Input(placeholder="A mysterious sickness has struck the overseer", id="incident")
        yield Static("", classes="detail", id="spark")
        yield Static("", classes="detail", id="starters")

    def enter(self, setup: Setup) -> None:
        """Show the quest starters of the world so far."""
        text = _starters_text(quest_starters(self.walkthrough.data, setup))
        self.query_one("#starters", Static).update(text)

    def action_roll(self) -> None:
        """Roll the action and theme oracles."""
        spark = roll_spark(self.walkthrough.data, self.walkthrough.rng)
        self.query_one("#spark", Static).update(f"Oracle: {spark}")

    def apply(self, setup: Setup) -> None:
        """Set the incident."""
        setup.inciting_incident = self.query_one("#incident", Input).value.strip()


class SceneStep(Step):
    """How play starts, the opening scene, and the first vow."""

    section = SECTIONS[5]
    title = "Starting play"
    rules = (
        "Begin in media res, in the middle of things, as your inciting incident happens, and "
        "Swear an Iron Vow to face it. Or begin with the normal world, in a prologue, and "
        "swear the vow when the incident comes. Give the vow a rank of troublesome, "
        "dangerous, or formidable."
    )
    keys = "Tab next field · Up and down or 1-3 choose"

    def compose(self) -> ComposeResult:
        """Lay out the start, the scene, and the vow."""
        yield ChoiceList([text for _, text in STARTS], 0, id="start")
        yield Label("Scene (optional)")
        yield Input(placeholder="The overseer's longhouse", id="scene")
        yield Label("Vow", classes="vow")
        yield Input(placeholder="Heal the overseer", id="vow", classes="vow")
        yield Label("Rank", classes="vow")
        yield ChoiceList(
            [rank.name.capitalize() for rank in VOW_RANKS], 1, id="rank", classes="vow"
        )

    @on(ChoiceList.Changed, "#start")
    def show_vow(self, event: ChoiceList.Changed) -> None:
        """Ask for the vow only in media res."""
        media_res = event.index == 0
        for widget in self.query(".vow"):
            widget.display = media_res
            widget.disabled = not media_res

    def _media_res(self) -> bool:
        return self.query_one("#start", ChoiceList).selected == 0

    def check(self) -> str | None:
        """Need a vow in media res."""
        if self._media_res() and not self.query_one("#vow", Input).value.strip():
            return "Write the vow your character swears."
        return None

    def apply(self, setup: Setup) -> None:
        """Set the start, the scene, and the vow."""
        setup.start = "in_media_res" if self._media_res() else "prologue"
        setup.scene = self.query_one("#scene", Input).value.strip()
        setup.vow = self.query_one("#vow", Input).value.strip() if self._media_res() else ""
        selected = self.query_one("#rank", ChoiceList).selected
        setup.vow_rank = VOW_RANKS[selected if selected is not None else 1]


def review_text(data: Datasworn, setup: Setup) -> str:
    """Summarize the setup for the review step."""
    stats = ", ".join(f"{stat} {setup.stats[stat]}" for stat in STAT_ORDER if stat in setup.stats)
    assets: list[str] = []
    for pick in setup.assets:
        asset = data.asset(pick.id)
        line = asset.name
        if "name" in pick.fields:
            line += f" ({pick.fields['name']})"
        if pick.ability is not None:
            line += f", ability {pick.ability}"
        assets.append(line)
    truths = [
        f"{truth.name}: {truth.options[setup.truths[truth_id]].description}"
        for truth_id, truth in data.truths.items()
        if truth_id in setup.truths
    ]
    where = ", ".join(
        part
        for part in (setup.place, data.regions[setup.region].name if setup.region else "")
        if part
    )
    lines = [
        f"[b]{escape(setup.name)}[/b], {escape(setup.description)}",
        f"Stats: {stats}",
        f"Assets: {escape('; '.join(assets))}",
        f"Harm: {setup.harm}",
        f"Where your story begins: {escape(where or 'not set')}",
        f"Bonds: {escape('; '.join(setup.bonds) or 'none yet')}",
        f"Background vow: {escape(setup.background_vow)} ({setup.background_rank.name.lower()})",
        f"Inciting incident: {escape(setup.inciting_incident or 'not set')}",
    ]
    if setup.start == "in_media_res":
        lines.append(
            f"Start: in media res, swearing {escape(setup.vow)} ({setup.vow_rank.name.lower()})"
        )
    else:
        lines.append("Start: the normal world, with a prologue")
    lines.append(f"Scene: {escape(setup.scene or 'not set')}")
    lines.append(f"World truths: {len(truths)} chosen, {len(data.truths) - len(truths)} blank")
    return "\n\n".join(["\n".join(lines), *(escape(truth) for truth in truths)])


class ReviewStep(Step):
    """Everything, to confirm before play."""

    section = SECTIONS[6]
    title = "Your choices"
    rules = "Check your choices. Go back to change one, or create the campaign and play."

    def compose(self) -> ComposeResult:
        """Lay out the summary."""
        yield Static("", id="summary")

    def enter(self, setup: Setup) -> None:
        """Summarize the answers."""
        self.query_one("#summary", Static).update(review_text(self.walkthrough.data, setup))


class Walkthrough(App[Setup | None]):
    """Walks a new player through campaign setup, step by step."""

    TITLE = "ironsworn-tui"
    CSS = """
    Screen { padding: 0 1; }
    #heading { margin-top: 1; width: 100%; }
    #rules { margin: 1 0; }
    #steps { height: 1fr; border: round $accent; padding: 0 1; }
    #error { color: $warning; width: 100%; }
    #keys { width: 100%; }
    """
    # A focused control's own Enter, such as an input's, comes first.
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "previous_step", show=False),
        Binding("enter", "next_step", show=False),
    ]
    ENABLE_COMMAND_PALETTE = False

    def __init__(
        self,
        data: Datasworn,
        rng: random.Random,
        name: str = "",
        taken: Callable[[str], bool] = lambda _: False,
    ) -> None:
        """Create the walkthrough.

        Args:
            data: The Datasworn data.
            rng: The source of the oracle rolls.
            name: A name to start the name step with.
            taken: True for a name a campaign already uses.
        """
        super().__init__()
        self.data = data
        self.rng = rng
        self.setup = Setup(name="", description="", stats={}, assets=[])
        count = len(data.truths)
        self.steps: list[Step] = [
            NameStep(name, taken),
            StatsStep(),
            AssetsStep(data),
            AssetDetailsStep(data),
            EquipmentStep(),
            *(
                TruthStep(truth, number, count)
                for number, truth in enumerate(data.truths.values(), 1)
            ),
            PlaceStep(data),
            BondsStep(),
            BackgroundVowStep(),
            IncidentStep(),
            SceneStep(),
            ReviewStep(),
        ]
        for number, step in enumerate(self.steps):
            step.id = f"step-{number}"
            step.walkthrough = self
        self.index = 0

    def compose(self) -> ComposeResult:
        """Lay out the heading, rules line, steps, error line, and keys."""
        yield Label(id="heading")
        yield Static(id="rules")
        with ContentSwitcher(id="steps", initial=self.steps[0].id):
            yield from self.steps
        yield Label(id="error")
        yield Label(id="keys")

    def on_mount(self) -> None:
        """Show the first step."""
        self.show(0)

    @property
    def step(self) -> Step:
        """The step on screen."""
        return self.steps[self.index]

    def show(self, index: int) -> None:
        """Show a step, brought up to date with the answers so far."""
        self.index = index
        step = self.steps[index]
        step.enter(self.setup)
        self.query_one(ContentSwitcher).current = step.id
        section = SECTIONS.index(step.section) + 1
        heading = Text.assemble(
            (step.section, "bold"),
            f": {step.title}   ",
            (f"Step {section} of {len(SECTIONS)}", "dim"),
        )
        self.query_one("#heading", Label).update(heading)
        self.query_one("#rules", Static).update(escape(step.rules))
        self.show_error("")
        keys = [step.keys] if step.keys else []
        keys.append("Enter create and play" if isinstance(step, ReviewStep) else "Enter next")
        if self._previous(index) is not None:
            keys.append("Esc back")
        keys.append("Ctrl+Q quit")
        self.query_one("#keys", Label).update(f"[dim]{escape(' · '.join(keys))}[/dim]")
        self.call_after_refresh(self._focus_first)

    def _focus_first(self) -> None:
        controls = self._controls()
        if controls:
            controls[0].focus(scroll_visible=False)
        else:
            self.step.focus(scroll_visible=False)
        self.step.scroll_home(animate=False)

    def _controls(self) -> list[Widget]:
        return [
            widget
            for widget in self.step.query("ChoiceList, StatGrid, AssetList, Input")
            if widget.focusable
        ]

    def show_error(self, text: str) -> None:
        """Show a problem with the step, or a note such as a roll, or clear it."""
        self.query_one("#error", Label).update(escape(text))

    def _next(self, index: int) -> int | None:
        for later in range(index + 1, len(self.steps)):
            if not self.steps[later].skipped(self.setup):
                return later
        return None

    def _previous(self, index: int) -> int | None:
        for earlier in range(index - 1, -1, -1):
            if not self.steps[earlier].skipped(self.setup):
                return earlier
        return None

    def next_step(self) -> None:
        """Finish the step and show the next one, or finish the walkthrough at the review."""
        step = self.step
        problem = step.check()
        if problem is not None:
            self.show_error(problem)
            return
        step.apply(self.setup)
        if isinstance(step, ReviewStep):
            self.finish()
            return
        later = self._next(self.index)
        if later is not None:
            self.show(later)

    def action_next_step(self) -> None:
        """Finish the step, as Enter does on a step with no control that takes it."""
        self.next_step()

    def finish(self) -> None:
        """Check the whole setup, and return it."""
        try:
            begin_campaign(self.data, self.setup)
        except (ValueError, AssetError, UnknownIdError) as error:
            message = str(error)
            self.show_error(message[:1].upper() + message[1:])
            return
        self.exit(self.setup)

    def action_previous_step(self) -> None:
        """Show the step before, keeping this step's answers."""
        earlier = self._previous(self.index)
        if earlier is not None:
            self.show(earlier)

    def roll_rest(self, first: TruthStep) -> None:
        """Roll for a truth and every truth after it, then show the step after the truths."""
        start = self.steps.index(first)
        last = start
        for index in range(start, len(self.steps)):
            step = self.steps[index]
            if not isinstance(step, TruthStep):
                break
            step.roll()
            step.apply(self.setup)
            last = index
        later = self._next(last)
        if later is not None:
            self.show(later)

    @on(Advance)
    def advance(self, event: Advance) -> None:
        """Move from a control to the next one, or to the next step from the last one."""
        self._advance_from(event.source)

    @on(Input.Submitted)
    def submitted(self, event: Input.Submitted) -> None:
        """Move from an input to the next control, or to the next step from the last one."""
        self._advance_from(event.input)

    def _advance_from(self, control: Widget) -> None:
        controls = self._controls()
        if control in controls and control is not controls[-1]:
            controls[controls.index(control) + 1].focus()
        else:
            self.next_step()
