from models import AppContext

from .utils import Context, parse_idx_notation


def refresh(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.refresh_all()


def quit_app(app_ctx: AppContext, ctx: Context) -> None:
    app_ctx.quit()


def add_change(app_ctx: AppContext, ctx: Context) -> None:
    raw_number = ctx["number"]
    raw_instance = ctx["instance"]

    if not raw_number.isdigit():
        app_ctx.status_msg = f'[red]Invalid change number: "{raw_number}"[/red]'
        return

    number = int(raw_number)

    if not raw_instance:
        instance = app_ctx.config.default_instance.name
    elif raw_instance.isdigit():
        idx = int(raw_instance)
        if idx < 1 or idx > len(app_ctx.config.instances):
            app_ctx.status_msg = f"[red]No instance at index {idx}[/red]"
            return
        instance = app_ctx.config.instances[idx - 1].name
    else:
        instance = raw_instance

    app_ctx.add_change(number, instance)


def toggle_waiting(app_ctx: AppContext, ctx: Context) -> None:
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.toggle_waiting(idx)


def handle_deletion(app_ctx: AppContext, ctx: Context) -> None:
    if ctx["idx"] == "x":
        app_ctx.purge_deleted()
        return

    if ctx["idx"] == "r":
        app_ctx.restore_all()
        return

    if ctx["idx"] == "c":
        app_ctx.delete_all_submitted()
        return

    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.toggle_deleted(idx)


def toggle_disable(app_ctx: AppContext, ctx: Context) -> None:
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.toggle_disabled(idx)


def open_change(app_ctx: AppContext, ctx: Context) -> None:
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.open_change_webui(idx)


def set_automerge(app_ctx: AppContext, ctx: Context) -> None:
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.review_set_automerge(idx)


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
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.add_comment(idx, ctx["text"])


def comment_replace_all(app_ctx: AppContext, ctx: Context) -> None:
    """Replace all comments with a single new comment."""
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.replace_all_comments(idx, ctx["text"])


def comment_edit_last(app_ctx: AppContext, ctx: Context) -> None:
    """Edit the last comment on a change."""
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.edit_last_comment(idx, ctx["text"])


def comment_delete(app_ctx: AppContext, ctx: Context) -> None:
    """Delete a comment or all comments."""
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    if (cidx := parse_idx_notation(ctx["comment_idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid comment idx parsed from: {ctx['comment_idx']}[/red]"
        return

    app_ctx.delete_comment(idx, cidx)


def review_abandon_action(app_ctx: AppContext, ctx: Context) -> None:
    if ctx.get("confirm") != "y":
        app_ctx.status_msg = "[yellow]Abandon cancelled[/yellow]"
        return

    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.review_abandon(idx)


def review_rebase_action(app_ctx: AppContext, ctx: Context) -> None:
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.review_rebase(idx)


def review_restore_action(app_ctx: AppContext, ctx: Context) -> None:
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.review_restore(idx)


def review_submit_action(app_ctx: AppContext, ctx: Context) -> None:
    if not (confirm := ctx.get("confirm")) or confirm.lower() != "y":
        app_ctx.status_msg = "[yellow]Submit cancelled[/yellow]"
        return

    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    app_ctx.review_submit(idx)


def review_code_review_action(app_ctx: AppContext, ctx: Context) -> None:
    if (idx := parse_idx_notation(ctx["idx"])) is None:
        app_ctx.status_msg = f"[red]Invalid idx parsed from: {ctx['idx']}[/red]"
        return

    raw = ctx.get("score", "")
    try:
        score = int(raw)
    except ValueError:
        app_ctx.status_msg = f"[red]Invalid score: {raw}[/red]"
        return

    app_ctx.review_code_review(idx, score)
