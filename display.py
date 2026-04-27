from datetime import datetime
from typing import Iterable

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from changes import Changes
from config import AppConfig
from models import ApprovalEntry, TrackedChange


def get_approvals_list(ch: TrackedChange) -> list[ApprovalEntry]:
    submitted = [a for a in ch.approvals if a.label == "SUBM"]
    return submitted if submitted else ch.approvals


def format_value(value_str: str) -> Text:
    try:
        v = int(value_str)
    except (ValueError, TypeError):
        return Text(value_str)
    if v >= 2:
        return Text(f"+{v}", style="bold green")
    if v == 1:
        return Text(f"+{v}", style="green")
    if v == 0:
        return Text(f" {v}", style="dim")
    if v == -1:
        return Text(str(v), style="yellow")
    return Text(str(v), style="bold red")


def approvals_to_text(approvals: Iterable[ApprovalEntry]) -> Text:
    approvals_text = Text()

    for appr in approvals:
        approvals_text.append(f"{appr.label}: ")
        approvals_text.append_text(format_value(appr.value))
        if appr.by:
            approvals_text.append(f" ({appr.by})", style="dim")
        approvals_text.append("\n")

    approvals_text = approvals_text[:-1]

    return approvals_text


def enumerate_comments(comments: Iterable[str]) -> str:
    return "\n".join(f"{idx}. {comment}" for idx, comment in enumerate(comments, 1))


def build_table(
    changes: Changes,
    config: AppConfig,
    status_msg: str = "",
    ssh_requests: int = 0,
    hints: str = "",
) -> Table:
    # TODO config.py should produce message with config summary
    caption = f"[dim]config:[/dim] {config.path} | [dim]interval:[/dim] {config.interval}s"

    if hints:
        caption = f"{caption}\n{hints}"

    if status_msg:
        caption = f"{status_msg}\n{caption}"

    table = Table(
        caption=caption,
        expand=True,
        box=None,
        show_edge=False,
        row_styles=["", "on #1a1a2e"],
        pad_edge=False,
    )
    table.add_column("idx", style="dim", no_wrap=True, width=2)
    table.add_column("Number", style="magenta", no_wrap=True, width=6)
    table.add_column("Project", no_wrap=True)
    table.add_column("Subject", max_width=60)
    table.add_column("Comments", no_wrap=False, ratio=50)
    table.add_column("Approvals", no_wrap=False, ratio=25)

    for idx, ch in enumerate(changes.get_all(), 1):
        styles = {
            "idx": "dim",
            "number": "magenta",
            "subject": "",
            "project": "",
            "approvals": "",
            "row": "",
            "comments": "",
        }

        if ch.error:
            table.add_row(str(idx), str(ch.number), Text(f"ERROR: {ch.error}", style="red"), "", "", "")
            continue

        if ch.url:
            styles["number"] += f" link {ch.url}"

        number_text = str(ch.number) if ch.number is not None else "<unknown>"
        subject_text = ch.subject or "<unknown>"
        project_text = ch.project or "<unknown>"

        if len(project_text.split("/")) > 2:
            project_text = "/".join(project_text.split("/")[-2:])
        approvals_text = Text()

        if ch.approvals:
            approvals = get_approvals_list(ch)
            approvals_text = approvals_to_text(approvals)
            approvals_text.style = styles["approvals"]

            if any(appr.label == "SUBM" for appr in approvals):
                styles["row"] = "on #019424"
            elif any(appr.value == "-2" for appr in approvals):
                styles["row"] = "on #320000"
            elif any(appr.value == "-1" for appr in approvals):
                styles["row"] = "on #8B4000"
            elif any((appr.value == "2" and appr.label == "Verified") for appr in approvals):
                styles["row"] = "on #177428"
            elif any((appr.value == "1" and appr.label == "Verified") for appr in approvals):
                styles["row"] = "on #1e5944"

        if ch.deleted:
            styles["subject"] += " strike dim"
            styles["project"] += " dim"
            styles["row"] = " on #1c1c1c"
            styles["comments"] += " dim strike"

            approvals_text = Text("deleted", style="dim red")

        elif ch.disabled:
            styles["subject"] += " dim italic"
            styles["project"] += " dim"
            styles["row"] = "on #1c1c1c"
            styles["comments"] += " dim italic"

            approvals_text = Text("disabled", style="dim yellow")

        elif ch.waiting:
            styles["row"] = "dim on #2a2a2a"

        comments_text = enumerate_comments(ch.comments) if ch.comments else ""

        table.add_row(
            Text(str(idx), style=styles["idx"]),
            Text(number_text, style=styles["number"]),
            Text(project_text, style=styles["project"]),
            Text(subject_text, style=styles["subject"]),
            Text(comments_text, style=styles["comments"]),
            approvals_text,
            style=styles["row"],
        )

    return table


def build_header(ssh_requests: int = 0) -> Panel:
    """Build a header Panel with timestamp and SSH request count.

    Args:
        ssh_requests: Number of SSH requests made.

    Returns:
        A Panel with centered header information.
    """
    header_text = f"Gerrit Approvals  (refreshed {datetime.now():%H:%M:%S})  ssh requests: {ssh_requests}"
    centered_text = Text(header_text, justify="center")
    return Panel(centered_text, expand=True, style="")


def build_layout(header: Panel, table: Table, prompt: str | None) -> Group:
    """Compose a layout with header, optional prompt, and table.

    Args:
        header: The header Panel.
        table: The data table to display (includes hints in caption at bottom).
        prompt: Optional prompt message (if empty or None, not included).

    Returns:
        A Group containing (in order):
        - Header Panel
        - Prompt text (only if non-empty)
        - Table (with hints in caption at bottom)
    """
    renderables: list = [header]

    if prompt:
        renderables.append(Text.from_markup(prompt, style="bold yellow"))

    renderables.append(table)

    return Group(*renderables)
