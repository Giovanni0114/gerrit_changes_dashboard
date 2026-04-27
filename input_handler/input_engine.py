from dataclasses import dataclass
from typing import Callable, Iterable

from models import AppContext
from utils import Arrow

from .context_actions import (
    add_change,
    comment_add,
    comment_delete,
    comment_edit_last,
    comment_replace_all,
    fetch_my_changes,
    handle_deletion,
    open_change,
    open_changes_in_editor,
    open_config_in_editor,
    quit_app,
    refresh,
    review_abandon_action,
    review_code_review_action,
    review_rebase_action,
    review_restore_action,
    review_submit_action,
    set_automerge,
    toggle_disable,
    toggle_waiting,
)
from .utils import Context, InputField, code_review_hint, generate_hints, instances_hint, parse_idx_notation

PROMPT_PER_LAST_KEY = {
    "a": "Add change",
    "w": "Toggle waiting",
    "d": "Toggle disabled",
    "x": "Toggle deletion",
    "o": "Open change in web UI",
    "e": "Editor",
    "c": "Comment",
    "r": "Review",
}


@dataclass(frozen=True)
class LeafAction:
    action: Callable[[AppContext, Context], None] | None
    required_inputs: list[InputField]
    label: str | None = None


# extra chars for rich index notation chars (, - space).
_IDX_EXTRA = frozenset({",", "-", " "})


def input_idx_factory(add_special_chars: set[str] | None = None) -> InputField:
    spec_chars = {"a"}
    if add_special_chars:
        spec_chars.update(add_special_chars)

    return InputField("idx", frozenset(spec_chars), True, _IDX_EXTRA)


TEXT_FIELD = InputField("text")
COMMENT_IDX_FIELD = InputField("comment_idx", frozenset({"a"}), digits_only=True)
CONFIRM_FIELD = InputField("confirm", frozenset({"y", "n"}))
SCORE_FIELD = InputField(
    "score", digits_only=True, extra_chars=frozenset({"+", "-"}), special_hint_func=code_review_hint
)

NUMBER_FIELD = InputField("number", digits_only=True)
INSTANCE_FIELD = InputField("instance", special_hint_func=instances_hint)

TOP_LEVEL_ACTIONS = {
    " ": LeafAction(None, [], "Changes actions"),
    "r": LeafAction(refresh, [], "Refresh"),
    "q": LeafAction(quit_app, [], "Quit"),
    "f": LeafAction(fetch_my_changes, [], "Fetch"),
    "a": LeafAction(add_change, [NUMBER_FIELD, INSTANCE_FIELD], "Add change"),
    "e": LeafAction(None, [], "Editor"),
}

# --- Comment sub-actions ---
COMMENT_ACTIONS: dict[str, LeafAction] = {
    "a": LeafAction(comment_add, [input_idx_factory(), TEXT_FIELD], "add"),
    "A": LeafAction(comment_replace_all, [input_idx_factory(), TEXT_FIELD], "replace all"),
    "e": LeafAction(comment_edit_last, [input_idx_factory(), TEXT_FIELD], "edit last"),
    "d": LeafAction(comment_delete, [input_idx_factory(), COMMENT_IDX_FIELD], "delete"),
}

# --- Review sub-actions ---
REVIEW_ACTIONS: dict[str, LeafAction] = {
    "a": LeafAction(review_abandon_action, [input_idx_factory(), CONFIRM_FIELD], "abandon"),
    "b": LeafAction(review_rebase_action, [input_idx_factory()], "rebase"),
    "R": LeafAction(review_restore_action, [input_idx_factory()], "restore"),
    "c": LeafAction(review_code_review_action, [input_idx_factory(), SCORE_FIELD], "code-review"),
    "s": LeafAction(review_submit_action, [input_idx_factory(), CONFIRM_FIELD], "submit"),
    "m": LeafAction(set_automerge, [input_idx_factory()], "automerge"),
}


LEADER_ACTIONS: dict[str, LeafAction] = {
    "w": LeafAction(toggle_waiting, [input_idx_factory()], "Toggle waiting"),
    "d": LeafAction(toggle_disable, [input_idx_factory()], "Toggle disabled"),
    "x": LeafAction(handle_deletion, [input_idx_factory({"x", "a"})], "Toggle deletion"),
    "o": LeafAction(open_change, [input_idx_factory()], "Open change"),
    "c": LeafAction(None, [], "Comment"),  # submenu
    "r": LeafAction(None, [], "Review"),  # submenu
}

EDITOR_ACTIONS: dict[str, LeafAction] = {
    "c": LeafAction(open_config_in_editor, [], "config"),
    "a": LeafAction(open_changes_in_editor, [], "changes"),
}


def key_allowed_in_sequence(key: str, sequence: Iterable[str]) -> bool:
    if key == "<enter>":
        return True

    match sequence:
        case []:
            return key in TOP_LEVEL_ACTIONS
        case [" "]:
            return key in LEADER_ACTIONS
        case ["e"]:
            return key in EDITOR_ACTIONS
        case [" ", "r"]:
            return key in REVIEW_ACTIONS
        case [" ", "c"]:
            return key in COMMENT_ACTIONS

    return False


def match_action(sequence: list[str]) -> LeafAction | None:
    if not sequence:
        return None

    match sequence:
        case [key]:
            return TOP_LEVEL_ACTIONS.get(key, None)
        case ["e", key]:
            return EDITOR_ACTIONS.get(key, None)
        case [" ", key]:
            return LEADER_ACTIONS.get(key, None)
        case [" ", "c", key]:
            return COMMENT_ACTIONS.get(key, None)
        case [" ", "r", key]:
            return REVIEW_ACTIONS.get(key, None)
    return None


class InputHandler:
    def __init__(self, app_ctx: AppContext):
        self.app_context = app_ctx

        self.sequence: list[str] = []
        self.input: str | None = None
        self.current_field: InputField | None = None
        self.context: dict[str, str] = {}
        self.current_action: LeafAction | None = None

    def hints(self) -> str:
        """Return keyboard shortcut hints for the current input state."""
        match self.sequence:
            case []:
                return generate_hints(TOP_LEVEL_ACTIONS)
            case ["e"]:
                return generate_hints(EDITOR_ACTIONS)
            case [" "]:
                return generate_hints(LEADER_ACTIONS)
            case [" ", "c"]:
                return generate_hints(COMMENT_ACTIONS)
            case [" ", "r"]:
                return generate_hints(REVIEW_ACTIONS)
        return ""

    def prompt(self) -> str:
        if len(self.sequence) == 0:
            return ""

        if self.input is not None and self.current_field is not None:
            if self.current_action and self.current_action.label:
                hint = self.current_action.label
            else:
                hint = PROMPT_PER_LAST_KEY.get(self.sequence[-1], "")

            special_hint = ""
            if special := self.current_field.special_chars:
                special_hint = f" [{' / '.join(sorted(special))}]"
            elif self.current_field.special_hint_func is not None:
                func_hint = self.current_field.special_hint_func(self.app_context)
                special_hint += f"({func_hint})"

            hint += f": {self.current_field.name}: {self.input}_{special_hint} [ESC=cancel]"
            return hint

        return PROMPT_PER_LAST_KEY.get(self.sequence[-1], "")

    def handle_key(self, key: str | Arrow) -> None:
        if isinstance(key, Arrow):
            # TODO: arrow navigation
            return

        if key == "<esc>":
            self.reset()
            return

        if self.input is not None:
            completed = self._handle_input(key)
            if completed:
                self._try_execute()
            return

        if not key_allowed_in_sequence(key, self.sequence):
            self.app_context.status_msg = f"key not allowed in sequence : {key} {self.sequence}"
            return

        if key == "<enter>":
            if not self.sequence:
                return
        else:
            self.sequence.append(key)

        self._try_execute()

    def _try_execute(self) -> None:
        """Execute action if all fields collected, otherwise prompt for the next field."""
        if not self.sequence:
            return

        action = self.current_action or match_action(self.sequence)

        # No match yet or submenu marker — wait for more input.
        if action is None or action.action is None:
            return

        self.current_action = action

        for required_field in action.required_inputs:
            if required_field.name in self.context:
                continue

            prefill = self._prefill_for_field(action, required_field)
            if prefill is None:
                return
            self.input = prefill
            self.current_field = required_field
            return

        action.action(self.app_context, self.context)
        self.reset()

    def _prefill_for_field(self, action: LeafAction, field: InputField) -> str | None:
        if action.action is comment_edit_last and field.name == "text":
            idx = parse_idx_notation(self.context["idx"])

            if idx is None or not idx.single():
                self.app_context.status_msg = f"[red]Invalid idx: {idx}[/red]"
                self.reset()
                return None

            change = self.app_context.changes.at(idx - 1)

            if not change or not change.comments:
                self.app_context.status_msg = "[red]No comments to edit[/red]"
                self.reset()
                return None

            return change.comments[-1]
        return ""

    def reset(self) -> None:
        self.input = None
        self.current_field = None
        self.sequence = []
        self.context = {}
        self.current_action = None

    def _handle_input(self, key: str) -> bool:
        """Process a key while in input mode. Returns True if the field is now complete."""
        assert self.current_field is not None

        if key == "<enter>":
            self.context[self.current_field.name] = self.input or ""
            self.input = None
            self.current_field = None
            return True

        if key == "<bs>":
            self.input = (self.input or "")[:-1]
            return False

        if key in self.current_field.special_chars:
            self.context[self.current_field.name] = key
            self.input = None
            self.current_field = None
            return True

        if self.current_field.digits_only and not key.isdigit() and key not in self.current_field.extra_chars:
            return False

        self.input = (self.input or "") + key
        return False

    def selected_rows(self) -> set[int]:
        pass
