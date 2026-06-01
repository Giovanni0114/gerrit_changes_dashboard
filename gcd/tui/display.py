from datetime import datetime
from typing import Iterable, List

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from gcd.core.config import AppConfig
from gcd.core.models import ApprovalEntry, TrackedChange


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


def enumerate_comments(comments: List[str]) -> str:
    if len(comments) == 1:
        return comments[0]

    return "\n".join(f"{idx}. {comment}" for idx, comment in enumerate(comments, 1))


def build_footer(
    config: AppConfig,
    status_msg: str = "",
    hints: str = "",
) -> Text:
    caption = f"[dim]config:[/dim] {config.path} | {config.generate_rich_footnote()}"

    if hints:
        caption += f"\n[dim]{hints}[/dim]"

    if status_msg:
        caption = f"{status_msg}\n{caption}"

    return Text.from_markup(caption, justify="center")


def build_table(
    changes: list[TrackedChange],
    selected_rows: frozenset[int] | None = None,
    header_text: str | None = None,
) -> Table:
    table = Table(
        expand=True,
        box=None,
        show_edge=False,
        row_styles=["", "on #1a1a2e"],
        pad_edge=False,
        title=header_text,
        title_style="bold white reverse",
    )

    if header_text is None:
        table.add_column("idx", style="dim", no_wrap=True, width=2)

    table.add_column("Number", style="magenta", no_wrap=True, width=6)
    table.add_column("Project", no_wrap=True, width=20)
    table.add_column("Subject", max_width=50, no_wrap=True, width=50)
    table.add_column("Comments", no_wrap=False, ratio=40)
    table.add_column("Approvals", no_wrap=False, ratio=35)

    selected = selected_rows or frozenset()
    for idx, ch in enumerate(changes, 1):
        styles = {
            "idx": "dim",
            "number": "magenta",
            "subject": "",
            "project": "",
            "approvals": "",
            "row": "",
            "comments": "",
        }

        if ch.url:
            styles["number"] += f" link {ch.url}"

        number_text = str(ch.number) if ch.number is not None else "<unknown>"
        subject_text = ch.subject or "<unknown>"
        project_text = ch.project or "<unknown>"
        comments_text = None
        approvals_text = Text()

        if len(project_text.split("/")) > 2:
            project_text = "/".join(project_text.split("/")[-2:])

        if ch.error:
            comments_text = f"ERROR: {ch.error}"
            styles["comments"] = "red"

        elif ch.approvals:
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
            styles["project"] += " strike dim"
            styles["row"] = " on #1c1c1c"

            approvals_text = Text("deleted", style="dim red")

        elif ch.disabled:
            styles["row"] = "italic dim on #1c1c1c"

            approvals_text = Text("disabled", style="dim yellow")

        elif ch.abandoned:
            styles["subject"] += " strike dim"
            styles["project"] += " strike dim"
            styles["row"] = "on #1c1c1c"

            approvals_text = Text("ABANDONED", style="red dim")

        elif ch.is_wip:
            approvals_text = Text("WIP", style="bright_black")

        elif ch.waiting:
            styles["row"] = "on #2a2a2a"

        if idx in selected:
            styles["subject"] += " underline"
            styles["project"] += " underline"

        comments_text = comments_text or enumerate_comments(ch.comments)

        elements = [] if header_text else [Text(str(idx), style=styles["idx"])]

        elements.extend(
            [
                Text(number_text, style=styles["number"]),
                Text(project_text, style=styles["project"]),
                Text(subject_text, style=styles["subject"]),
                Text(comments_text, style=styles["comments"]),
            ]
        )

        table.add_row(
            *elements,
            approvals_text,
            style=styles["row"],
        )

    return table


def build_header(ssh_requests: int = 0) -> Panel:
    header_text = f"Gerrit Approvals  (refreshed {datetime.now():%H:%M:%S})  ssh requests: {ssh_requests}"
    centered_text = Text(header_text, justify="center")
    return Panel(centered_text, expand=True, style="")


def build_layout(
    header: RenderableType, tables: list[Table], footer: RenderableType, prompt: str | None, show_header: bool = False
) -> Group:
    renderables: list = []

    if show_header:
        renderables.append(header)

    if prompt:
        renderables.append(Text.from_markup(prompt, style="bold yellow"))

    for table in tables:
        renderables.append(table)

    renderables.append(footer)
    return Group(*renderables)
