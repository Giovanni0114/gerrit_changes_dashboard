import importlib
import pkgutil
import traceback
from typing import List, Type

from gcd.core.models import AppContext, BasePlugin


class PluginLoadError(Exception):
    pass


def discover_plugin_classes(package_name: str) -> List[Type[BasePlugin]]:
    classes = []

    package = importlib.import_module(package_name)

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        try:
            module = importlib.import_module(f"{package_name}.{module_name}")

            if hasattr(module, "plugin_class"):
                cls = module.plugin_class

                if not issubclass(cls, BasePlugin):
                    raise PluginLoadError(f"{cls} is not BasePlugin")

                classes.append(cls)

        except Exception:
            print(f"[PLUGIN LOAD ERROR] {module_name}")
            traceback.print_exc()

    return classes


class PluginManager:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.plugins: List[BasePlugin] = []

        # cfg = self.config.get(plugin.name, {})

        # if not cfg.get("enabled", True):
        #     return

        # self.plugins.append(plugin)

        self.plugins = [plg(True) for plg in discover_plugin_classes("gcd.plugins")]

    def setup(self):
        for plugin in self.plugins:
            self._safe_call(plugin, "setup")

    def init(self):
        for plugin in self.plugins:
            self._safe_call(plugin, "on_init")

    def emit(self, event: str):
        for plugin in self.plugins:
            self._safe_call(plugin, event)

    def shutdown(self):
        for plugin in reversed(self.plugins):
            self._safe_call(plugin, "on_exit")

    def _safe_call(self, plugin: BasePlugin, method: str):
        try:
            if fn := getattr(plugin, method, None):
                fn(self.ctx)
        except Exception:
            print(f"[PLUGIN ERROR] {plugin.name}.{method}")
            traceback.print_exc()
