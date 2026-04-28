import importlib
import pkgutil
import traceback
from typing import List, Type

from gcd.core.models import AppContext, BasePlugin, PluginEvent
from gcd.core.logs import app_logger


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


_logger = app_logger()


class PluginManager:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.plugins: List[BasePlugin] = []

        enabled_plugins = ctx.config.get_all_enabled_plugins()

        self.plugins = [plg(ctx) for plg in discover_plugin_classes("gcd.plugins") if plg.name in enabled_plugins]

    def setup(self):
        """Called on start of application"""
        for plugin in self.plugins:
            self._safe_call(plugin, "setup")

    def init(self):
        """Called when app is ready and changes are loaded"""
        for plugin in self.plugins:
            self._safe_call(plugin, "on_init")

    def emit(self, event: PluginEvent, source_instance: str, args=None, kwargs=None):
        """Called on specific events"""
        instance = self.ctx.config.get_instance_by_name(source_instance)
        plugins = [pl for pl in self.plugins if pl.name in instance.enabled_plugins]

        for plugin in plugins:
            self._safe_call(plugin, f"on_{event}", args=args, kwargs=kwargs)

    def shutdown(self):
        for plugin in self.plugins:
            self._safe_call(plugin, "on_exit")

    def _safe_call(self, plugin: BasePlugin, method: str, args=None, kwargs=None):
        try:
            if fn := getattr(plugin, method, None):
                fn(*(args or []), **(kwargs or {}))
        except Exception:
            _logger.error(f"[PLUGIN ERROR] {plugin.name}.{method}: {traceback.format_exc()}")
