from gcd.core.models import BasePlugin


class LoggerPlugin(BasePlugin):
    name = "logger"
    version = "0.0.1"

    def on_init(self):
        self.log.info("on_init")

    def on_exit(self) -> None:
        self.log.info("on_exit")

    def on_activate(self) -> None:
        self.log.info("on_activate")


plugin_class = LoggerPlugin
