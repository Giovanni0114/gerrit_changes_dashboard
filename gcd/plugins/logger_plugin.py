from gcd.core.models import BasePlugin, ChangeIdentifier, TrackedChange


class LoggerPlugin(BasePlugin):
    name = "logger"
    version = "0.0.1"

    def on_init(self):
        self.log.info("on_init")

    def on_exit(self) -> None:
        self.log.info("on_exit")

    def on_activate(self, change_id: ChangeIdentifier, change: TrackedChange) -> None:
        self.log.info(f"on_activate {change_id}")


plugin_class = LoggerPlugin
