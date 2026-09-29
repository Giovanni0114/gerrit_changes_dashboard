from gcd.core.models import ChangeIdentifier, TrackedChange
from gcd.plugins.neo_comment_errors import CommentCatcher


class CommentsContext:
    def __init__(self, response: dict[str, list[dict[str, object]]]) -> None:
        self.response = response

    def fetch_comments_from_change(self, ch: TrackedChange) -> list[dict[str, object]]:
        return self.response["comments"]


def test_comment_catcher_skips_non_string_comment_messages() -> None:
    plugin = CommentCatcher(
        CommentsContext({"comments": [{"message": 1}]}),
        "prod",
        {
            "start_gate_message": "gate started",
            "start_check_message": "check started",
            "finish_messages": ["finished"],
            "buildset_link_prefix": "buildset",
            "job_line_prefix": "job",
            "success_labels": ["SUCCESS"],
            "failure_labels": ["FAILURE"],
        },
    )
    plugin.on_init()
    change = TrackedChange(number=123, instance="prod")

    plugin.on_activate(ChangeIdentifier(123, "prod"), change)

    assert change.comments == []
