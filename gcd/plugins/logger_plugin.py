from gcd.core.models import AppContext, BasePlugin


class LoggerPlugin(BasePlugin):
    name = "logger"
    version = "0.1.2"

    def setup(self, ctx: AppContext) -> None:
        self.log("setup")

    def on_init(self, ctx: AppContext):
        self.log("on_init")

    def on_exit(self, ctx: AppContext) -> None:
        self.log("on_exit")

    def on_activate(self, ctx: AppContext) -> None:
        self.log("on_activate")


plugin_class = LoggerPlugin
