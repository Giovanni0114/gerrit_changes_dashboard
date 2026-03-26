from datetime import datetime

from rich.table import Table
from rich.text import Text

from models import Change


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


def build_table(
    changes: list[Change],
    results: dict[tuple[str, str], dict],
    config_path: str,
    interval: float,
    status_msg: str = "",
    prompt_msg: str = "",
) -> Table:
    """Build the Rich table displaying all changes and their approvals.

    Note: The inline SUBM check below looks at the LAST patchset only.
    This is intentionally different from gerrit.is_submitted() which checks ALL patchsets.
    """
    caption = (
        f"[dim]config:[/dim] {config_path} | [dim]interval:[/dim] {interval}s"
        f" | [dim]a[/dim] add  [dim]w[/dim] wait  [dim]d[/dim] disable  [dim]x[/dim] delete  [dim]q[/dim] quit"
    )
    if status_msg:
        caption = f"{status_msg}\n{caption}"
    table = Table(
        title=f"Gerrit Approvals  (refreshed {datetime.now():%H:%M:%S})",
        caption=caption,
        expand=True,
        box=None,
        show_edge=False,
        row_styles=["", "on #1a1a2e"],
        pad_edge=False,
    )
    table.add_column("#", style="dim", no_wrap=True, width=3)
    table.add_column("Number", style="magenta", no_wrap=True)
    table.add_column("Commit", style="cyan", no_wrap=True)
    table.add_column("Subject", max_width=60)
    table.add_column("Project", no_wrap=True)
    table.add_column("Approvals")

    if prompt_msg:
        table.add_row("", "", "", Text(prompt_msg, style="bold yellow"), "", "")

    for idx, ch in enumerate(changes, 1):
        short = ch.hash[:7]
        data = results.get((ch.host, ch.hash), {})

        if ch.deleted:
            subject = Text(data.get("subject", ""), style="strike dim")
            number_str = str(data.get("number", ""))
            table.add_row(
                str(idx),
                Text(number_str, style="dim"),
                Text(short, style="dim"),
                subject,
                Text(data.get("project", ""), style="dim"),
                Text("deleted", style="dim red"),
                style="on #1c1c1c",
            )
            continue

        if ch.disabled:
            subject = Text(data.get("subject", ""), style="dim italic")
            number_str = str(data.get("number", ""))
            table.add_row(
                str(idx),
                Text(number_str, style="dim"),
                Text(short, style="dim"),
                subject,
                Text(data.get("project", ""), style="dim"),
                Text("disabled", style="dim yellow"),
                style="on #1c1c1c",
            )
            continue

        if "error" in data:
            table.add_row(str(idx), "", short, Text(data["error"], style="red"), "", "")
            continue

        url = data.get("url", "")
        style = "magenta"
        if url:
            style += f" link {url}"
        number_text = Text(str(data.get("number", "")), style=style)

        subject = Text(data.get("subject", ""))
        project = data.get("project", "<unknown>")

        patch_sets = data.get("patchSets", [])
        approvals_text = Text()
        row_style = None
        if patch_sets:
            approvals = patch_sets[-1].get("approvals", [])
            is_submitted = any(appr.get("type", "?") == "SUBM" for appr in approvals)
            if is_submitted:
                approvals = [appr for appr in approvals if appr.get("type", "?") == "SUBM"]
            seen = set()
            for appr in approvals:
                key = (appr.get("type", ""), appr.get("by", {}).get("name", ""))
                if key in seen:
                    continue
                seen.add(key)

                if appr.get("type", "?") == "SUBM":
                    row_style = "on #019424"
                elif appr.get("value") in ("1", "2") and appr.get("type", "?") == "Verified":
                    row_style = row_style or "on #1e5944"
                elif appr.get("value") == "-2" and appr.get("type", "?") == "Verified":
                    row_style = "on #320000"
                elif appr.get("value") == "-1":
                    row_style = "on #8B4000"

                if approvals_text:
                    approvals_text.append("\n")
                approvals_text.append(f"{appr.get('type', '?')}: ")
                approvals_text.append_text(format_value(appr.get("value")))
                by_name = appr.get("by", {}).get("name", "")
                if by_name:
                    approvals_text.append(f" ({by_name})", style="dim")

        table.add_row(
            str(idx),
            number_text,
            short,
            subject,
            project,
            approvals_text,
            style="dim on #2a2a2a" if ch.waiting else row_style,
        )

    return table
