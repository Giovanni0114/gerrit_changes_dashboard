from dataclasses import dataclass, field
from typing import Callable, Iterable

from models import AppContext
from utils import Arrow

Context = dict[str, str]

PROMPTS_FOR_LAST_KEY = {
    "a": "Add change (number)",
    "w": "Toggle waiting",
    "d": "Toggle disabled",
    "x": "Toggle deletion",
    "o": "Open change in web UI",
    "s": "Set Automerge +1",
    "e": "Editor",
    "c": "Comment",
}

# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class InputField:
    name: str
    special_chars: frozenset[str] = field(default_factory=frozenset)
    digits_only: bool = False
    extra_chars: frozenset[str] = field(default_factory=frozenset)
    special_hint_func: Callable[[AppContext], str] | None = None


# --------------------------------------------------------------------------------


def validator_int(input: str) -> bool:
    return input.isnumeric()


def parse_idx_notation(raw: str, max_idx: int) -> list[int] | None:
    """Parse advanced index notation into a sorted list of unique 1-based indexes.

    Supported formats:
    - Single index: ``"3"``
    - Comma-separated: ``"3,2,4"``
    - Range: ``"3-8"`` (inclusive on both ends)
    - Combined: ``"1-2, 3-5, 11, 23"``

    Whitespace is ignored. Returns ``None`` when the expression is invalid or any
    index falls outside ``[1, max_idx]``.
    """
    if not raw or not raw.strip():
        return None

    stripped = raw.replace(" ", "")
    if not stripped:
        return None

    result: set[int] = set()
    for part in stripped.split(","):
        if not part:
            return None  # empty segment, e.g. "1,,3"
        if "-" in part:
            pieces = part.split("-")
            if len(pieces) != 2 or not pieces[0] or not pieces[1]:
                return None
            if not pieces[0].isnumeric() or not pieces[1].isnumeric():
                return None
            lo, hi = int(pieces[0]), int(pieces[1])
            if lo > hi:
                return None
            if lo < 1 or hi > max_idx:
                return None
            result.update(range(lo, hi + 1))
        else:
            if not part.isnumeric():
                return None
            val = int(part)
            if val < 1 or val > max_idx:
                return None
            result.add(val)

    return sorted(result) if result else None


def validate_idx(raw: str, num_changes: int) -> int | None:
    """Validate a single raw index string against the current changes count.

    Returns the 1-based index as ``int`` on success, ``None`` on failure.
    Rejects non-numeric input, zero, negative values, and out-of-range indexes.
    """
    if not raw.isnumeric():
        return None
    val = int(raw)
    if val < 1 or val > num_changes:
        return None
    return val


# --------------------------------------------------------------------------------


def refresh(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.refresh_all()


def quit_app(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.quit()


# --------------------------------------------------------------------------------


def add_change(app_ctx: AppContext, ctx: Context) -> None:
    raw_number = ctx["number"]
    raw_instance = ctx["instance"]

    if not raw_number.isdigit() or int(raw_number) == 0:
        app_ctx.status_msg = f'[red]Invalid change number: "{raw_number}"[/red]'
        return

    number = int(raw_number)

    if raw_instance == "":
        instance = app_ctx.config.default_instance.name
    elif raw_instance.isdigit():
        idx = int(raw_instance)
        if idx < 1 or idx > len(app_ctx.config.instances):
            app_ctx.status_msg = f"[red]No instance at index {idx}[/red]"
            return
        instance = app_ctx.config.instances[idx - 1].name
    else:
        instance = raw_instance

    if not instance:
        app_ctx.status_msg = "[red]No instance specified[/red]"
        return

    app_ctx.add_change(number, instance)


def toggle_waiting(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    if idx == "a":
        app_ctx.toggle_all_waiting()
        return

    indexes = parse_idx_notation(idx, len(app_ctx.changes))
    if indexes is None:
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    for i in indexes:
        app_ctx.toggle_waiting(i)


def handle_deletion(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    if idx == "a":
        app_ctx.delete_all_submitted()
        return

    if idx == "x":
        app_ctx.purge_deleted()
        return

    if idx == "r":
        app_ctx.restore_all()
        return

    indexes = parse_idx_notation(idx, len(app_ctx.changes))
    if indexes is None:
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    for i in indexes:
        app_ctx.toggle_deleted(i)


def toggle_disable(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    if idx == "a":
        app_ctx.toggle_all_disabled()
        return

    indexes = parse_idx_notation(idx, len(app_ctx.changes))
    if indexes is None:
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    for i in indexes:
        app_ctx.toggle_disabled(i)


def open_change(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    indexes = parse_idx_notation(idx, len(app_ctx.changes))
    if indexes is None:
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    for i in indexes:
        app_ctx.open_change_webui(i)


def set_automerge(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    indexes = parse_idx_notation(idx, len(app_ctx.changes))

    if indexes is None:
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    for i in indexes:
        app_ctx.set_automerge(i)


def open_config_in_editor(app_ctx: AppContext, ctx: Context) -> None:
    """Open the TOML config file in the configured editor."""
    app_ctx.open_config_in_editor()


def open_changes_in_editor(app_ctx: AppContext, ctx: Context) -> None:
    """Open the approvals/changes file in the configured editor."""
    app_ctx.open_changes_in_editor()


def fetch_my_changes(app_ctx: AppContext, ctx: Context) -> None:
    """Fetch all open changes owned by the user from Gerrit."""
    app_ctx.fetch_open_changes()


def comment_add(app_ctx: AppContext, ctx: Context) -> None:
    """Add a comment to a change."""
    app_ctx.add_comment(int(ctx["idx"]), ctx["text"])


def comment_replace_all(app_ctx: AppContext, ctx: Context) -> None:
    """Replace all comments with a single new comment."""
    app_ctx.replace_all_comments(int(ctx["idx"]), ctx["text"])


def comment_edit_last(app_ctx: AppContext, ctx: Context) -> None:
    """Edit the last comment on a change."""
    app_ctx.edit_last_comment(int(ctx["idx"]), ctx["text"])


def comment_delete(app_ctx: AppContext, ctx: Context) -> None:
    """Delete a comment or all comments."""
    cidx = ctx["comment_idx"]
    row = int(ctx["idx"])
    if cidx == "a":
        app_ctx.delete_all_comments(row)
    else:
        app_ctx.delete_comment(row, int(cidx))


# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class SubAction:
    action: Callable[[AppContext, Context], None]
    required_inputs: list[InputField]


@dataclass(frozen=True)
class LeafAction:
    action: Callable[[AppContext, Context], None]
    required_inputs: list[InputField]


@dataclass(frozen=True)
class MenuAction:
    required_inputs: list[InputField]
    sub_actions: dict[str, SubAction]


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

# --- Comment sub-actions ---
COMMENT_SUBACTIONS: dict[str, SubAction] = {
    "a": SubAction(comment_add, [TEXT_FIELD]),
    "A": SubAction(comment_replace_all, [TEXT_FIELD]),
    "e": SubAction(comment_edit_last, [TEXT_FIELD]),
    "d": SubAction(comment_delete, [COMMENT_IDX_FIELD]),
}


def _instances_hint(app_ctx: AppContext) -> str:
    if not app_ctx.config.instances:
        return "No instances configured"
    return "Instances: " + ", ".join(f"{idx + 1}={inst.name}" for idx, inst in enumerate(app_ctx.config.instances))


LEADER_ACTIONS: dict[str, Action | None] = {
    "a": LeafAction(
        add_change, [InputField("number", digits_only=True), InputField("instance", special_hint_func=_instances_hint)]
    ),
    "w": LeafAction(toggle_waiting, [InputField("idx", frozenset({"a"}), digits_only=True, extra_chars=_IDX_EXTRA)]),
    "d": LeafAction(toggle_disable, [InputField("idx", frozenset({"a"}), digits_only=True, extra_chars=_IDX_EXTRA)]),
    "x": LeafAction(
        handle_deletion,
        [InputField("idx", frozenset({"a", "x", "r"}), digits_only=True, extra_chars=_IDX_EXTRA)],
    ),
    "o": LeafAction(open_change, [InputField("idx", digits_only=True, extra_chars=_IDX_EXTRA)]),
    "s": LeafAction(set_automerge, [InputField("idx", digits_only=True, extra_chars=_IDX_EXTRA)]),
    "c": MenuAction([IDX_FIELD], COMMENT_SUBACTIONS),
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

    last = sequence[-1]

    match sequence:
        case ["e", key]:
            return EDITOR_ACTIONS.get(key, None)

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
        self.current_action: LeafAction | None = None

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
                "[bold]s[/] automerge  "
                "[bold]c[/] comment"
            )

        return "[bold]Space[/] Changes  [bold]q[/] quit  [bold]r[/] refresh  [bold]f[/] fetch  [bold]e[/] editor  "

    def prompt(self) -> str:
        if len(self.sequence) == 0:
            return ""

        # Show sub-action options if in sub-action selection mode
        if self.pending_sub_actions is not None:
            options = []
            for key in sorted(self.pending_sub_actions.keys()):
                if key == "a":
                    options.append("a=add")
                elif key == "A":
                    options.append("A=replace all")
                elif key == "e":
                    options.append("e=edit last")
                elif key == "d":
                    options.append("d=delete")
            return f"comment > {' / '.join(options)} [ESC=cancel]"

        if self.input is not None and self.current_field is not None:
            hint = PROMPTS_FOR_LAST_KEY.get(self.sequence[-1], "")
            special_hint = ""
            if special := self.current_field.special_chars:
                special_hint = f" [{' / '.join(sorted(special))}]"

            elif self.current_field.special_hint_func is not None:
                func_hint = self.current_field.special_hint_func(self.app_context)
                special_hint += f"({func_hint})"

            hint += f": {self.current_field.name}: {self.input}_{special_hint} [ESC=cancel]"
            return hint

        return PROMPTS_FOR_LAST_KEY.get(self.sequence[-1], "")

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
                    self._start_field_collection()
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
