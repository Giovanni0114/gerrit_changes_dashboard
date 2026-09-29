"""TC-301..309 — selection parsing and config startup."""

from __future__ import annotations

import pytest

from gcd.core.config import (
    DEFAULT_CACHE_FILENAME,
    DEFAULT_CHANGES_FILENAME,
    DEFAULT_INTERVAL,
    DEFAULT_LOG_DIRNAME,
    DEFAULT_REFRESH_RATE,
    AppConfig,
    Layout,
)
from gcd.tui.input_handler.utils import parse_idx_notation

# --- parse_idx_notation ---


def test_single_index():
    # TC-301
    result = parse_idx_notation("3")
    assert result is not None
    assert result.values == frozenset({3})
    assert result.wildcard is False


def test_comma_separated():
    # TC-302
    assert parse_idx_notation("3,2,4").values == frozenset({2, 3, 4})


def test_inclusive_range():
    # TC-303
    assert parse_idx_notation("3-6").values == frozenset({3, 4, 5, 6})


def test_combined_with_whitespace():
    # TC-304
    assert parse_idx_notation("1-2, 3, 11").values == frozenset({1, 2, 3, 11})


def test_wildcard():
    # TC-305
    result = parse_idx_notation("a")
    assert result is not None
    assert result.wildcard is True
    assert result.values == frozenset()


@pytest.mark.parametrize("raw", ["", "1-", "x", "3-1"])
def test_invalid_inputs_return_none(raw):
    # TC-306
    assert parse_idx_notation(raw) is None


# --- AppConfig ---


def test_loads_instances_from_toml(config):
    # TC-307
    names = [ins.name for ins in config.instances]
    assert names == ["prod", "staging"]

    prod = config.get_instance_by_name("prod")
    assert prod is not None
    assert prod.host == "gerrit.example.com"
    assert prod.port == 22


def test_applies_defaults(tmp_path):
    # TC-308 — omitted interval / ui_refresh_rate fall back to documented defaults
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[config]\n"
        "default_port = 22\n"
        'default_email = "t@e.com"\n'
        'changes_file = "./changes.json"\n'
        'cache_file = "./cache.json"\n'
        'log_dir = "./log"\n'
        "\n[instance.prod]\n"
        'host = "gerrit.example.com"\n'
    )
    config = AppConfig(cfg)

    assert config.interval == DEFAULT_INTERVAL
    assert config.ui_refresh_rate == DEFAULT_REFRESH_RATE


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("interval", '"7"', 7),
        ("interval", "8", 8),
        ("interval", "9.9", 9),
        ("interval", "true", 1),
        ("ui_refresh_rate", '"7.5"', 7.5),
        ("ui_refresh_rate", "8", 8.0),
        ("ui_refresh_rate", "9.5", 9.5),
        ("ui_refresh_rate", "true", 1.0),
    ],
)
def test_numeric_config_fields_accept_values_convertible_by_python(tmp_path, key, value, expected):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[config]\n"
        "default_port = 22\n"
        'default_email = "t@e.com"\n'
        f"{key} = {value}\n"
        "\n[instance.prod]\n"
        'host = "gerrit.example.com"\n',
        encoding="utf-8",
    )

    config = AppConfig(cfg)

    assert getattr(config, key) == expected


def test_hide_tags_preserves_mixed_list_values(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[config]\n"
        "default_port = 22\n"
        'default_email = "t@e.com"\n'
        'hide_tags = ["#HIDE", 1, 2.5, true]\n'
        "\n[instance.prod]\n"
        'host = "gerrit.example.com"\n',
        encoding="utf-8",
    )

    assert AppConfig(cfg).hide_tags == ["#HIDE", 1, 2.5, True]


def test_empty_path_config_values_use_defaults(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[config]\n"
        "default_port = 22\n"
        'default_email = "t@e.com"\n'
        'changes_file = ""\n'
        'cache_file = ""\n'
        'log_dir = ""\n'
        "\n[instance.prod]\n"
        'host = "gerrit.example.com"\n',
        encoding="utf-8",
    )

    config = AppConfig(cfg)

    assert config.changes_path == (tmp_path / DEFAULT_CHANGES_FILENAME).resolve()
    assert config.cache_path == (tmp_path / DEFAULT_CACHE_FILENAME).resolve()
    assert config.log_path == (tmp_path / DEFAULT_LOG_DIRNAME).resolve()


def test_next_layout_cycles(config):
    # TC-309
    start = config.layout
    seen = [start]
    for _ in range(len(list(Layout))):
        seen.append(config.next_layout())

    # cycled through every layout and wrapped back to the start
    assert set(seen) == set(Layout)
    assert seen[-1] == start


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("interval", "[]"),
        ("ui_refresh_rate", "[]"),
        ("changes_file", "[]"),
        ("cache_file", "[]"),
        ("log_dir", "[]"),
        ("hide_tags", '"#HIDE"'),
        ("editor", "[]"),
    ],
)
def test_config_fields_reject_values_of_the_wrong_type(tmp_path, key, value):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[config]\n"
        "default_port = 22\n"
        'default_email = "t@e.com"\n'
        f"{key} = {value}\n"
        "\n[instance.prod]\n"
        'host = "gerrit.example.com"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=key):
        AppConfig(cfg)
