import importlib
import pkgutil
import traceback
from typing import Type

from gcd.core.logs import app_logger
from gcd.core.models import AppContext, BasePlugin, PluginEvent


class PluginLoadError(Exception):
    pass


_logger = app_logger()


def discover_plugin_classes(package_name: str) -> dict[str, Type[BasePlugin]]:
    classes = {}

    package = importlib.import_module(package_name)

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        try:
            module = importlib.import_module(f"{package_name}.{module_name}")

            if hasattr(module, "plugin_class"):
                cls = module.plugin_class

                if not issubclass(cls, BasePlugin):
                    raise PluginLoadError(f"{cls} is not BasePlugin")

                classes[cls.name] = cls

        except Exception:
            _logger.error(f"[PLUGIN LOAD ERROR] {module_name}")
            traceback.print_exc()

    return classes


class PluginManager:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

        enabled_plugins_per_instance = ctx.config.get_enabled_plugins_per_instance()
        plugin_classes = discover_plugin_classes("gcd.plugins")

        self.plugins_per_instance: dict[str, list[BasePlugin]] = {ins.name: [] for ins in ctx.config.instances}

        for instance in enabled_plugins_per_instance:
            for plugin in enabled_plugins_per_instance[instance]:
                if plugin not in plugin_classes:
                    raise ValueError(f"Plugin {plugin} defined for instance {instance} doesn't exits!")
                config = ctx.config.get_config_for_plugin(plugin, instance)
                self.plugins_per_instance[instance].append(plugin_classes[plugin](ctx, instance, config))

    @property
    def plugins(self) -> list[BasePlugin]:
        return [pl for pls in self.plugins_per_instance.values() for pl in pls]

    def init(self) -> None:
        for plugin in self.plugins:
            self._safe_call(plugin, "on_init")

    def emit(self, event: PluginEvent, source_instance: str, *args, **kwargs) -> None:
        instance = self.ctx.config.get_instance_by_name(source_instance)

        if not instance:
            _logger.error(f"Error during emitting event {event} Unknown instance: {source_instance}")
            return

        for plugin in self.plugins_per_instance.get(instance.name, []):
            self._safe_call(plugin, f"on_{event}", args=args, kwargs=kwargs)

    def shutdown(self) -> None:
        for plugin in self.plugins:
            self._safe_call(plugin, "on_exit")

    def _safe_call(self, plugin: BasePlugin, method: str, args=None, kwargs=None) -> None:
        try:
            if fn := getattr(plugin, method, None):
                fn(*(args or []), **(kwargs or {}))
            else:
                _logger.error(f"[PLUGIN ERROR] {plugin.name}: method {method} not found")
        except Exception:
            _logger.error(f"[PLUGIN ERROR] {plugin.name}.{method}: {traceback.format_exc()}")
