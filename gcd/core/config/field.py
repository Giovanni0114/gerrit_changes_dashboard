from dataclasses import dataclass
from pathlib import Path

from .parsers import Parser


@dataclass(frozen=True)
class Field:
    attr: str
    key: str
    parse: Parser
    example: str | None = None
    comment: str | None = None

    def read(self, config_data: dict, base_dir: Path) -> object:
        return self.parse(self.key, config_data.get(self.key), base_dir)
