from gcd.core.models import ApprovalEntry, BasePlugin, ChangeIdentifier, TrackedChange

KEY_START_GATE = "start_gate_message"
KEY_START_CHECK = "start_check_message"
KEY_FINISH_MESSAGES = "finish_messages"
KEY_BUILDSET_LINK_PREFIX = "buildset_link_prefix"
KEY_JOB_LINE_PREFIX = "job_line_prefix"
KEY_SUCCESS_LABELS = "success_labels"
KEY_FAILURE_LABELS = "failure_labels"

REQUIRED_CONFIG_KEYS = [
    KEY_START_GATE,
    KEY_START_CHECK,
    KEY_FINISH_MESSAGES,
    KEY_BUILDSET_LINK_PREFIX,
    KEY_JOB_LINE_PREFIX,
    KEY_SUCCESS_LABELS,
    KEY_FAILURE_LABELS,
]


class CommentCatcher(BasePlugin):
    name = "comment_catcher"
    version = "0.0.2"

    def on_init(self) -> None:
        missing = [key for key in REQUIRED_CONFIG_KEYS if key not in self.config]
        if missing:
            self.enabled = False
            self.log.error(f"on_init: init failed, missing required config keys: {', '.join(missing)}")
            return

        self.start_gate_message: str = self.config[KEY_START_GATE]
        self.start_check_message: str = self.config[KEY_START_CHECK]
        self.finish_messages: list[str] = list(self.config[KEY_FINISH_MESSAGES])
        self.buildset_link_prefix: str = self.config[KEY_BUILDSET_LINK_PREFIX]
        self.job_line_prefix: str = self.config[KEY_JOB_LINE_PREFIX]
        self.success_labels: list[str] = list(self.config[KEY_SUCCESS_LABELS])
        self.failure_labels: list[str] = list(self.config[KEY_FAILURE_LABELS])

        self.log.info("on_init: plugin initialized")

    def on_exit(self) -> None:
        pass

    def on_activate(self, change_id: ChangeIdentifier, ch: TrackedChange) -> None:
        self.log.info(f"on_activate: {change_id}")

        comments = self.ctx.fetch_comments_from_change(ch)
        if not isinstance(comments, list):
            self.log.error(f"on_activate: could not fetch comments for {change_id}: {comments}")
            return

        # Walk newest -> oldest and act on the first CI comment we recognise.
        for comment in reversed(comments):
            msg = comment.get("message", "") if isinstance(comment, dict) else ""
            if not msg:
                continue

            self.log.debug(msg)

            if self._handle_ci_comment(ch, msg):
                return

    def _handle_ci_comment(self, ch: TrackedChange, msg: str) -> bool:
        if self.start_gate_message in msg:
            return self._record_pipeline_start(ch, msg, self.start_gate_message, "Gate")

        if self.start_check_message in msg:
            return self._record_pipeline_start(ch, msg, self.start_check_message, "Check")

        if any(marker in msg for marker in self.finish_messages):
            return self._record_gate_finish(ch, msg)

        return False

    def _record_pipeline_start(self, ch: TrackedChange, msg: str, marker: str, label: str) -> bool:
        link = msg.split(marker)[-1].strip()
        self.log.info(f"{label} started at {link}")

        ch.comments.append(f"{label} started at {link}")
        ch.modified = True
        return True

    def _record_gate_finish(self, ch: TrackedChange, msg: str) -> bool:
        lines = msg.splitlines()

        links = [line for line in lines if self.buildset_link_prefix in line]
        if not links:
            self.log.info(f"Buildset link not found in gate message: {msg}")
            return False

        link = links[0].strip()
        jobs = [line for line in lines if line.startswith(self.job_line_prefix)]
        succeeded = [job for job in jobs if any(label in job for label in self.success_labels)]
        failed = [job for job in jobs if any(label in job for label in self.failure_labels)]

        summary = f"{len(jobs)} found, {len(succeeded)} succeeded, {len(failed)} failed"
        self.log.info(f"Gate finished at {link}: {summary}")

        ch.comments.append(f"Gate finished at {link}: {summary}")
        if failed:
            ch.comments.extend(failed)
        ch.modified = True
        return True

    def on_new_approval(self, change_id: ChangeIdentifier, new_approval: ApprovalEntry) -> None:
        pass


plugin_class = CommentCatcher
