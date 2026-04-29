from gcd.core.models import ApprovalEntry, BasePlugin, ChangeIdentifier


class AuditPlugin(BasePlugin):
    name = "audit"
    version = "0.0.1"

    def setup(self) -> None:
        self.log.info("setup")

    def on_init(self):
        self.log.info("on_init")

    def on_exit(self) -> None:
        self.log.info("on_exit")

    def on_activate(self) -> None:
        self.log.info("on_activate")

    def on_new_change(self, change_id: ChangeIdentifier) -> None:
        self.log.info(f"on_new_change {change_id}")

    def on_new_comment(self, change_id: ChangeIdentifier, new_comment: str) -> None:
        self.log.info(f"on_new_comment {change_id}, new comments: {new_comment}")

    def on_new_approval(self, change_id: ChangeIdentifier, new_approval: ApprovalEntry) -> None:
        self.log.info(f"on_new_approval {change_id}, new approvals: {new_approval}")


plugin_class = AuditPlugin
