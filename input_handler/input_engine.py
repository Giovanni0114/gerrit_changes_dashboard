from dataclasses import dataclass
from typing import Callable, Iterable

from models import AppContext
from utils import Arrow

from .context_actions import (
    add_change,
    code_review_hint,
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
from .utils import Context, InputField, instances_hint

PROMPT_PER_LAST_KEY = {
    "a": "Add change (number)",
    "w": "Toggle waiting",
    "d": "Toggle disabled",
    "x": "Toggle deletion",
    "o": "Open change in web UI",
    "e": "Editor",
    "c": "Comment",
    "r": "Review",
}



@dataclass(frozen=True)
class SubAction:
    action: Callable[[AppContext, Context], None]
    required_inputs: list[InputField]
    prompt_label: str | None = None
    menu_label: str | None = None


@dataclass(frozen=True)
class LeafAction:
    action: Callable[[AppContext, Context], None]
    required_inputs: list[InputField]


@dataclass(frozen=True)
class MenuAction:
    required_inputs: list[InputField]
    sub_actions: dict[str, SubAction]
    label: str


Action = LeafAction | MenuAction


REFRESH_ACTION = LeafAction(refresh, [])
QUIT_ACTION = LeafAction(quit_app, [])
FETCH_ACTION = LeafAction(fetch_my_changes, [])

# Common InputField for index parameters — allows digits plus multi-index notation chars (, - space).
_IDX_EXTRA = frozenset({",", "-", " "})

# --- Input field definitions ---
IDX_FIELD = InputField("idx", digits_only=True)
TEXT_FIELD = InputField("text")
COMMENT_IDX_FIELD = InputField("comment_idx", frozenset({"a"}), digits_only=True)
CONFIRM_FIELD = InputField("confirm", frozenset({"y", "n"}))
SCORE_FIELD = InputField(
    "score",
    digits_only=True,
    extra_chars=frozenset({"+", "-"}),
    special_hint_func=code_review_hint,
)

# --- Comment sub-actions ---
COMMENT_SUBACTIONS: dict[str, SubAction] = {
    "a": SubAction(comment_add, [TEXT_FIELD], menu_label="a=add"),
    "A": SubAction(comment_replace_all, [TEXT_FIELD], menu_label="A=replace all"),
    "e": SubAction(comment_edit_last, [TEXT_FIELD], menu_label="e=edit last"),
    "d": SubAction(comment_delete, [COMMENT_IDX_FIELD], menu_label="d=delete"),
}

# --- Review sub-actions ---
REVIEW_SUBACTIONS: dict[str, SubAction] = {
    "a": SubAction(review_abandon_action, [CONFIRM_FIELD], "Abandon change #{idx}?", "a=abandon"),
    "b": SubAction(review_rebase_action, [], menu_label="b=rebase"),
    "R": SubAction(review_restore_action, [], menu_label="R=restore"),
    "c": SubAction(review_code_review_action, [SCORE_FIELD], "Code-Review change #{idx}", "c=code-review"),
    "s": SubAction(review_submit_action, [CONFIRM_FIELD], "Submit change #{idx}? irreversible", "s=submit"),
    "m": SubAction(set_automerge, [], "Automerge +1 change #{idx}", "m=automerge"),
}


LEADER_ACTIONS: dict[str, Action | None] = {
    "a": LeafAction(
        add_change, [InputField("number", digits_only=True), InputField("instance", special_hint_func=instances_hint)]
    ),
    "w": LeafAction(toggle_waiting, [InputField("idx", frozenset({"a"}), digits_only=True, extra_chars=_IDX_EXTRA)]),
    "d": LeafAction(toggle_disable, [InputField("idx", frozenset({"a"}), digits_only=True, extra_chars=_IDX_EXTRA)]),
    "x": LeafAction(
        handle_deletion,
        [InputField("idx", frozenset({"a", "x", "r"}), digits_only=True, extra_chars=_IDX_EXTRA)],
    ),
    "o": LeafAction(open_change, [InputField("idx", digits_only=True, extra_chars=_IDX_EXTRA)]),
    "c": MenuAction([IDX_FIELD], COMMENT_SUBACTIONS, "comment"),
    "r": MenuAction([IDX_FIELD], REVIEW_SUBACTIONS, "review"),
    "e": None,  # submenu — resolved in match_action via full sequence
}

EDITOR_ACTIONS: dict[str, LeafAction] = {
    "c": LeafAction(open_config_in_editor, []),
    "a": LeafAction(open_changes_in_editor, []),
}


def key_allowed_in_sequence(key: str, sequence: Iterable[str]) -> bool:
    if key == "<enter>":
        return True

    match sequence:
        case []:
            return key in (" ", "r", "q", "f", "e")
        case [" "]:
            return key in LEADER_ACTIONS
        case ["e"]:
            return key in EDITOR_ACTIONS

    return False


def match_action(sequence: list[str]) -> Action | None:
    if not sequence:
        return None

    match sequence:
        case ["e", key]:
            return EDITOR_ACTIONS.get(key, None)
        case [" ", key]:
            return LEADER_ACTIONS.get(key, None)

    last = sequence[-1]

    match last:
        case "r":
            return REFRESH_ACTION

        case "q":
            return QUIT_ACTION

        case "f":
            return FETCH_ACTION

        case _:
            action = LEADER_ACTIONS.get(last, None)
            return action


class InputHandler:
    def __init__(self, app_ctx: AppContext):
        self.app_context = app_ctx

        self.sequence: list[str] = []
        self.input: str | None = None
        self.current_field: InputField | None = None
        self.context: dict[str, str] = {}
        self.pending_sub_actions: dict[str, SubAction] | None = None
        self.pending_menu: MenuAction | None = None
        self.current_action: LeafAction | None = None
        self.active_sub_action: SubAction | None = None

    def hints(self) -> str:
        """Return keyboard shortcut hints for the current input state."""
        if self.sequence[:1] == ["e"]:
            return "[bold]c[/] config  [bold]a[/] approvals"
        elif self.sequence[:1] == [" "]:
            return (
                "[bold]a[/] add  "
                "[bold]w[/] wait  "
                "[bold]d[/] disable  "
                "[bold]x[/] delete  "
                "[bold]o[/] open  "
                "[bold]c[/] comment  "
                "[bold]r[/] review"
            )

        return "[bold]Space[/] Changes  [bold]q[/] quit  [bold]r[/] refresh  [bold]f[/] fetch  [bold]e[/] editor  "

    def prompt(self) -> str:
        if len(self.sequence) == 0:
            return ""

        if self.pending_sub_actions is not None:
            options = []
            for key in sorted(self.pending_sub_actions.keys()):
                sub = self.pending_sub_actions[key]
                if sub.menu_label:
                    options.append(sub.menu_label)

            label = self.pending_menu.label if self.pending_menu else ""

            return f"{label} > {' / '.join(options)} [ESC=cancel]"

        if self.input is not None and self.current_field is not None:
            if self.active_sub_action and self.active_sub_action.prompt_label:
                hint = self.active_sub_action.prompt_label.format(**self.context)
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
            # self.app_context.status_msg = f"Arrow detected: {key}"
            # TODO: create an handling for arrow navigation
            return

        if key == "<esc>":
            self.reset()
            return

        # Check if we're in sub-action selection mode
        if self.pending_sub_actions is not None:
            if key in self.pending_sub_actions:
                sub_action = self.pending_sub_actions[key]
                self.pending_sub_actions = None
                self.active_sub_action = sub_action
                self.current_action = LeafAction(sub_action.action, sub_action.required_inputs)

                # Special handling for 'e' (edit) sub-action - check if there are comments to edit
                if key == "e":
                    idx = int(self.context["idx"])
                    comments = self.app_context.changes[idx - 1].comments
                    if not comments:
                        self.app_context.status_msg = "[red]No comments to edit[/red]"
                        self.reset()
                        return
                    # Pre-fill with last comment
                    self._start_field_collection_with_prefill(comments[-1])
                else:
                    self._try_execute()
                return
            else:
                # Invalid sub-action key
                valid_keys = ", ".join(sorted(self.pending_sub_actions.keys()))
                self.app_context.status_msg = f"[red]Invalid option. Choose from: {valid_keys}[/red]"
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
        """Find the action for the current sequence and execute it, or enter input mode for next required field."""
        if not self.sequence:
            return

        action: Action | None = self.current_action or match_action(self.sequence)

        if action is None:
            return

        for required_field in action.required_inputs:
            if required_field.name not in self.context:
                self.input = ""
                self.current_field = required_field
                return

        # All fields collected
        if isinstance(action, LeafAction):
            action.action(self.app_context, self.context)
            self.reset()
        elif isinstance(action, MenuAction):
            self.pending_sub_actions = action.sub_actions
            self.pending_menu = action
            self.current_action = None

    def _start_field_collection(self) -> None:
        """Start collecting fields for the current action."""
        if self.current_action is None:
            return
        for required_field in self.current_action.required_inputs:
            if required_field.name not in self.context:
                self.input = ""
                self.current_field = required_field
                return

    def _start_field_collection_with_prefill(self, prefill: str) -> None:
        """Start collecting fields with pre-filled input for the first field."""
        if self.current_action is None:
            return
        for required_field in self.current_action.required_inputs:
            if required_field.name not in self.context:
                self.input = prefill
                self.current_field = required_field
                return

    def reset(self) -> None:
        self.input = None
        self.current_field = None
        self.sequence = []
        self.context = {}
        self.pending_sub_actions = None
        self.pending_menu = None
        self.current_action = None
        self.active_sub_action = None

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
