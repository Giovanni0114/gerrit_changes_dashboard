from models import AppContext

from .utils import Context, parse_idx_notation


def refresh(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.refresh_all()


def quit_app(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.quit()


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


def review_abandon_action(app_ctx: AppContext, ctx: Context) -> None:
    if ctx.get("confirm") != "y":
        app_ctx.status_msg = "[yellow]Abandon cancelled[/yellow]"
        return
    app_ctx.review_abandon(int(ctx["idx"]))


def review_rebase_action(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.review_rebase(int(ctx["idx"]))


def review_restore_action(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.review_restore(int(ctx["idx"]))


def review_submit_action(app_ctx: AppContext, ctx: Context) -> None:
    if ctx.get("confirm") != "y":
        app_ctx.status_msg = "[yellow]Submit cancelled[/yellow]"
        return
    app_ctx.review_submit(int(ctx["idx"]))


def review_code_review_action(app_ctx: AppContext, ctx: Context) -> None:
    raw = ctx["score"].strip()
    try:
        score = int(raw)
    except ValueError:
        app_ctx.status_msg = f"[red]Invalid score: {raw}[/red]"
        return
    if score < -2 or score > 2:
        app_ctx.status_msg = f"[red]Score out of range: {score}[/red]"
        return
    app_ctx.review_code_review(int(ctx["idx"]), score)
