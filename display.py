from datetime import datetime
from typing import Iterable

from rich.table import Table
from rich.text import Text

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

    # remove last newline
    approvals_text = approvals_text[:-1]

    return approvals_text


def build_table(
    changes: list[TrackedChange],
    config_path: str,
    interval: float,
    status_msg: str = "",
    prompt_msg: str = "",
    ssh_requests: int = 0,
    hints: str = "",
) -> Table:
    caption = f"[dim]config:[/dim] {config_path} | [dim]interval:[/dim] {interval}s \n{hints}"

    if status_msg:
        caption = f"{status_msg}\n{caption}"

    table = Table(
        title=f"Gerrit Approvals  (refreshed {datetime.now():%H:%M:%S})  ssh requests: {ssh_requests}",
        caption=caption,
        expand=True,
        box=None,
        show_edge=False,
        row_styles=["", "on #1a1a2e"],
        pad_edge=False,
    )
    table.add_column("idx", style="dim", no_wrap=True, width=2)
    table.add_column("Number", style="magenta", no_wrap=True, width=6)
    table.add_column("Subject", max_width=60)
    table.add_column("Project", no_wrap=True)
    table.add_column("Approvals", no_wrap=False, ratio=40)

    if prompt_msg:
        table.add_row("", "", Text(prompt_msg, style="bold yellow"), "", "")

    for idx, ch in enumerate(changes, 1):
        styles = {
            "idx": "dim",
            "number": "magenta",
            "subject": "",
            "project": "",
            "approvals": "",
            "row": "",
        }

        if ch.error:
            table.add_row(str(idx), "", Text(ch.error, style="red"), "", "")
            continue

        if ch.url:
            styles["number"] += f" link {ch.url}"

        number_text = str(ch.number) if ch.number is not None else "<unknown>"
        subject_text = ch.subject or "<unknown>"
        project_text = ch.project or "<unknown>"
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

            approvals_text = Text("deleted", style="dim red")

        elif ch.disabled:
            styles["subject"] += " dim italic"
            styles["project"] += " dim"
            styles["row"] = "on #1c1c1c"

            approvals_text = Text("disabled", style="dim yellow")

        elif ch.waiting:
            styles["row"] = "dim on #2a2a2a"

        table.add_row(
            Text(str(idx), style=styles["idx"]),
            Text(number_text, style=styles["number"]),
            Text(subject_text, style=styles["subject"]),
            Text(project_text, style=styles["project"]),
            approvals_text,
            style=styles["row"],
        )

    return table
