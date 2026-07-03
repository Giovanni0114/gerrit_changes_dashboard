from gcd.core.models import ApprovalEntry, BasePlugin, ChangeIdentifier, TrackedChange

REQUIRED_CONFIG_KEYS = [
    # "parser",
    # "line-regex",
]


START_GATE_MESSAGE = "Starting gate jobs: "
START_GATE_MESSAGE = "Starting check jobs: "
SUCCESS_GATE_MESSAGE = "Build succeeded (check pipeline)."
FAIL_GATE_MESSAGE = "Build failed (check pipeline)."

SUCCESS_LABELS = ["SUCCESS"]
FAILUE_LABELS = ["FAILURE"]


class CommentCatcher(BasePlugin):
    name = "comment_catcher"
    version = "0.0.1"

    def on_init(self):
        if all(key in self.config for key in REQUIRED_CONFIG_KEYS):
            self.log.info("on_init: plugin initialized")
        else:
            self.enabled = False
            self.log.error(
                "on_init: init failed, one or more of required fields are not configured:"
                f" {', '.join(REQUIRED_CONFIG_KEYS)}"
            )

    def on_exit(self) -> None:
        pass

    def on_activate(self, change_id: ChangeIdentifier, ch: TrackedChange) -> None:
        self.log.info(f"on_activate: {change_id}")
        comments = self.ctx.fetch_comments_from_change(ch)[::-1]

        for comment in comments:
            msg = comment["message"]

            self.log.debug(msg)

            if START_GATE_MESSAGE in msg:
                link = msg.split(START_GATE_MESSAGE)[-1]
                self.log.info(f"Gate started at {link}")

                ch.comments.append(f"Gate started at {link}")
                ch.modified = True
                return

            if START_CHECK_MESSAGE in msg:
                link = msg.split(START_CHECK_MESSAGE)[-1]
                self.log.info(f"Check started at {link}")

                ch.comments.append(f"Check started at {link}")
                ch.modified = True
                return

            if SUCCESS_GATE_MESSAGE in msg or FAIL_GATE_MESSAGE in msg:
                buildset_link_regex = "https://zuul.volvocars.net/t/vcc/buildset/"
                lines = msg.splitlines()
                link = [l for l in lines if buildset_link_regex in l]  # noqa: E741

                if not link:
                    self.log.info(f"Link not found in succeeded gate message {msg}")
                    return

                link = link[0]
                self.log.info(f"Gate finished at {link}")

                jobs = [l for l in lines if l.startswith("- ")]  # noqa: E741

                succsess = [l for l in jobs if any(label in l for label in SUCCESS_LABELS)]
                failures = [l for l in jobs if any(label in l for label in FAILUE_LABELS)]

                comment_msg = f"{len(jobs)} found, {len(succsess)} succeeded, {len(failures)} failed"

                self.log.info(comment_msg)

                ch.comments.append(f"Gate finished at {link}: {comment_msg}")

                if failures:
                    ch.comments.extend(failures)

                ch.modified = True
                return

    def on_new_approval(self, change_id: ChangeIdentifier, new_approval: ApprovalEntry) -> None:
        pass


plugin_class = CommentCatcher
