import sys

import pytest

from gcd.cli.query import build_query
from gcd.tui import app as app_module


def test_build_query_emits_quoted_hashtag_operator() -> None:
    operators = build_query({"hashtag": "needs review"}, None)

    assert operators == ['hashtag:"needs review"']


def test_main_passes_hashtag_argument_to_query(config_path, monkeypatch) -> None:
    received = []

    def fake_query_run(config, args) -> int:
        received.append(args.hashtag)
        return 0

    monkeypatch.setattr("gcd.cli.query.run", fake_query_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["gcd", "--config", str(config_path), "query", "--hashtag", "needs-review"],
    )

    with pytest.raises(SystemExit) as exit_info:
        app_module.main()

    assert exit_info.value.code == 0
    assert received == ["needs-review"]
