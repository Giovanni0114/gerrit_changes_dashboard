from datetime import datetime
from typing import Iterable

from rich.table import Table
from rich.text import Text

from models import Change


class Approval:
    def __init__(self, appr: dict) -> None:
        self.label = appr.get("type", "?")
        self.by = appr.get("by", {}).get("name", "")
        self.value = appr.get("value", "")


def get_approvals_list(approvals: list[dict]) -> Iterable[Approval]:
    approvals = [Approval(a) for a in approvals]
    submitted = [appr for appr in approvals if appr.label == "SUBM"]
    if submitted:
        return submitted

    return approvals


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


def approvals_to_text(approvals: Iterable[Approval]) -> Text:
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
    changes: list[Change],
    results: dict[tuple[str, str], dict],
    config_path: str,
    interval: float,
    status_msg: str = "",
    prompt_msg: str = "",
    ssh_requests: int = 0,
) -> Table:
    caption = (
        f"[dim]config:[/dim] {config_path} | "
        f"[dim]interval:[/dim] {interval}s \n"
        "[bold]a[/] add  "
        "[bold]w[/] wait  "
        "[bold]d[/] disable  "
        "[bold]x[/] delete  "
        "[bold]r[/] refresh  "
        "[bold]o[/] open  "
        "[bold]s[/] set automerge  "
        "[bold]q[/] quit  "
    )

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
    table.add_column("idx", style="dim", no_wrap=True, width=3)
    table.add_column("Number", style="magenta", no_wrap=True)
    table.add_column("Commit", style="cyan", no_wrap=True)
    table.add_column("Subject", max_width=60)
    table.add_column("Project", no_wrap=True)
    table.add_column("Approvals")

    if prompt_msg:
        table.add_row("", "", "", Text(prompt_msg, style="bold yellow"), "", "")

    for idx, ch in enumerate(changes, 1):
        styles = {
            "idx": "dim",
            "number": "magenta",
            "commit": "cyan",
            "subject": "",
            "project": "",
            "approvals": "",
            "row": "",
        }

        short_commit = ch.hash[:7]
        data = results.get((ch.host, ch.hash), {})

        if "error" in data:
            table.add_row(str(idx), "", short_commit, Text(data["error"], style="red"), "", "")
            continue

        url = data.get("url", None)
        if url:
            styles["number"] += f" link {url}"

        number_text = str(data.get("number", "<unknown>"))
        subject_text = data.get("subject", "<unknown>")
        project_text = data.get("project", "<unknown>")
        approvals_text = Text()

        patch_sets = data.get("patchSets", [])
        if patch_sets:
            approvals = get_approvals_list(patch_sets[-1].get("approvals", []))
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
            styles["commit"] += " dim"
            styles["project"] += " dim"
            styles["row"] = " on #1c1c1c"

            approvals_text = Text("deleted", style="dim red")

        elif ch.disabled:
            styles["subject"] += " dim italic"
            styles["commit"] += " dim"
            styles["project"] += " dim"
            styles["row"] = "on #1c1c1c"

            approvals_text = Text("disabled", style="dim yellow")

        elif ch.waiting:
            styles["row"] = "dim on #2a2a2a"

        table.add_row(
            Text(str(idx), style=styles["idx"]),
            Text(number_text, style=styles["number"]),
            Text(short_commit, style=styles["commit"]),
            Text(subject_text, style=styles["subject"]),
            Text(project_text, style=styles["project"]),
            approvals_text,
            style=styles["row"],
        )

    return table
