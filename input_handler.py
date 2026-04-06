from dataclasses import dataclass, field
from typing import Callable, Iterable

from models import AppContext

Context = dict[str, str]

PROMPTS_FOR_LAST_KEY = {
    "a": "Add change",
    "w": "Toggle waiting",
    "d": "Toggle disabled",
    "x": "Toggle deletion",
    "o": "Open change in web UI",
    "s": "Set Automerge +1",
}

# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class InputField:
    name: str
    special_chars: frozenset[str] = field(default_factory=frozenset)
    digits_only: bool = False


# --------------------------------------------------------------------------------


def validator_int(input: str):
    return input.isnumeric()


# --------------------------------------------------------------------------------


def refresh(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.refresh_all()


def quit_app(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.quit()


# --------------------------------------------------------------------------------


def add_change(app_ctx: AppContext, ctx: Context) -> None:
    hash = ctx["hash"]
    raw_host = ctx["host"]

    if len(hash) == 0:
        app_ctx.status_msg = f'[red]Invalid hash: "{hash}"[/red]'
        return

    if raw_host == "":
        host = app_ctx.default_host or ""
    elif raw_host.isdigit():
        idx = int(raw_host)
        if idx < 1 or idx > len(app_ctx.changes):
            app_ctx.status_msg = f"[red]No change at index {idx}[/red]"
            return
        host = app_ctx.changes[idx - 1].host
    else:
        host = raw_host

    if not host:
        app_ctx.status_msg = "[red]No host specified and no default_host configured[/red]"
        return

    app_ctx.add_change(hash, host)


def toggle_waiting(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    if idx == "a":
        app_ctx.toggle_all_waiting()
        return

    if not validator_int(idx):
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    app_ctx.toggle_waiting(int(idx))


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

    if not validator_int(idx):
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    app_ctx.toggle_deleted(int(idx))


def toggle_disable(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    if idx == "a":
        app_ctx.toggle_all_disabled()
        return

    if not validator_int(idx):
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    app_ctx.toggle_disabled(int(idx))


def open_change(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    if not validator_int(idx):
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    app_ctx.open_change_webui(int(idx))


def set_automerge(app_ctx: AppContext, ctx: Context) -> None:
    idx = ctx["idx"]

    if not validator_int(idx):
        app_ctx.status_msg = f"[red]Invalid idx: {idx} [/red]"
        return

    app_ctx.set_automerge(int(idx))


# --------------------------------------------------------------------------------


@dataclass
class Action:
    action: Callable[[AppContext, Context], None]
    required_inputs: list[InputField]


REFRESH_ACTION = Action(refresh, [])
QUIT_ACTION = Action(quit_app, [])

LEADER_ACTIONS = {
    "a": Action(add_change, [InputField("hash"), InputField("host")]),
    "w": Action(toggle_waiting, [InputField("idx", frozenset({"a"}), digits_only=True)]),
    "d": Action(toggle_disable, [InputField("idx", frozenset({"a"}), digits_only=True)]),
    "x": Action(handle_deletion, [InputField("idx", frozenset({"a", "x", "r"}), digits_only=True)]),
    "o": Action(open_change, [InputField("idx", digits_only=True)]),
    "s": Action(set_automerge, [InputField("idx", digits_only=True)]),
}


def key_allowed_in_sequence(key: str, sequence: Iterable[str]) -> bool:
    if key == "<enter>":
        return True

    match sequence:
        case []:
            return key in (" ", "r", "q")
        case [" "]:
            return key in LEADER_ACTIONS

    return False


def match_action(key: str):
    match key:
        case "r":
            return REFRESH_ACTION

        case "q":
            return QUIT_ACTION

        case _:
            return LEADER_ACTIONS.get(key, None)


class InputHandler:
    def __init__(self, app_ctx: AppContext):
        self.app_context = app_ctx

        self.sequence: list[str] = []
        self.input: str | None = None
        self.current_field: InputField | None = None
        self.context: dict[str, str] = {}

    def hints(self) -> str:
        """Return keyboard shortcut hints for the current input state."""
        if not self.sequence or self.sequence[0] != " ":
            return "[bold]Space[/] Changes  [bold]q[/] quit  [bold]r[/] refresh"
        return (
            "[bold]a[/] add  "
            "[bold]w[/] wait  "
            "[bold]d[/] disable  "
            "[bold]x[/] delete  "
            "[bold]o[/] open  "
            "[bold]s[/] automerge"
        )

    def prompt(self, num_changes: int) -> str:
        if len(self.sequence) == 0:
            return ""

        if self.input is not None and self.current_field is not None:
            hint = PROMPTS_FOR_LAST_KEY.get(self.sequence[-1], "")
            special = self.current_field.special_chars
            special_hint = f" [{' / '.join(sorted(special))}]" if special else ""
            hint += f": {self.current_field.name}: {self.input}_{special_hint} [ESC=cancel]"
            return hint

        return PROMPTS_FOR_LAST_KEY.get(self.sequence[-1], "")

    def handle_key(self, key: str) -> None:
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
        """Find the action for the current sequence and execute it, or enter input mode for next required field."""
        if not self.sequence:
            return

        action = match_action(self.sequence[-1])

        if action is None:
            return

        for required_field in action.required_inputs:
            if required_field.name not in self.context:
                self.input = ""
                self.current_field = required_field
                return

        action.action(self.app_context, self.context)
        self.reset()

    def reset(self) -> None:
        self.input = None
        self.current_field = None
        self.sequence = []
        self.context = {}

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

        if self.current_field.digits_only and not key.isdigit():
            return False

        self.input = (self.input or "") + key
        return False
