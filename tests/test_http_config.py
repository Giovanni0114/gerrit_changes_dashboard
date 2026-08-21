from __future__ import annotations

from pathlib import Path

import pytest

from gcd.core.config import AppConfig, generate_example_config
from gcd.core.models import GerritHttpConfig, GerritInstance


def _write_config(tmp_path: Path, instance_settings: str = "") -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f'[config]\ndefault_port = 22\n\n[instance.prod]\nhost = "gerrit-ssh.example.com"\n{instance_settings}',
        encoding="utf-8",
    )
    return path


def test_http_config_is_optional_for_existing_instances():
    instance = GerritInstance("prod", "gerrit.example.com", 22, "user@example.com")

    assert instance.http is None


def test_http_password_is_hidden_from_representations():
    secret = "do-not-display"
    http = GerritHttpConfig(
        url="https://gerrit.example.com",
        username="user",
        password=secret,
    )
    instance = GerritInstance(
        "prod",
        "gerrit.example.com",
        22,
        "user@example.com",
        http=http,
    )

    assert secret not in repr(http)
    assert secret not in repr(instance)


def test_ssh_only_config_has_no_http_settings(tmp_path):
    config = AppConfig(_write_config(tmp_path))

    assert config.default_instance.http is None


def test_http_url_uses_anonymous_defaults(tmp_path):
    config = AppConfig(
        _write_config(
            tmp_path,
            'http_url = "https://gerrit.example.com"\n',
        )
    )

    assert config.default_instance.http == GerritHttpConfig(
        url="https://gerrit.example.com",
        username=None,
        password=None,
        timeout=10.0,
        verify_tls=True,
    )


def test_all_http_settings_are_parsed(tmp_path):
    config = AppConfig(
        _write_config(
            tmp_path,
            'http_url = "http://gerrit.example.com:8080/review"\n'
            'http_username = "user"\n'
            'http_password = "token"\n'
            "http_timeout = 2.5\n"
            "http_verify_tls = false\n",
        )
    )

    assert config.default_instance.http == GerritHttpConfig(
        url="http://gerrit.example.com:8080/review",
        username="user",
        password="token",
        timeout=2.5,
        verify_tls=False,
    )


def test_http_url_trailing_slashes_are_removed(tmp_path):
    config = AppConfig(
        _write_config(
            tmp_path,
            'http_url = "https://gerrit.example.com/review///"\n',
        )
    )

    assert config.default_instance.http is not None
    assert config.default_instance.http.url == "https://gerrit.example.com/review"


@pytest.mark.parametrize(
    "setting",
    [
        'http_username = "user"',
        'http_password = "token"',
        "http_timeout = 5",
        "http_verify_tls = false",
    ],
)
def test_http_options_require_http_url(tmp_path, setting):
    with pytest.raises(ValueError, match=r"instance 'prod'.*http_url"):
        AppConfig(_write_config(tmp_path, f"{setting}\n"))


@pytest.mark.parametrize(
    "credentials",
    [
        'http_username = "user"\n',
        'http_password = "token"\n',
        'http_username = ""\nhttp_password = "token"\n',
        'http_username = "user"\nhttp_password = ""\n',
        'http_username = 7\nhttp_password = "token"\n',
        'http_username = "user"\nhttp_password = 7\n',
    ],
)
def test_http_credentials_must_be_nonempty_string_pair(tmp_path, credentials):
    with pytest.raises(ValueError, match=r"instance 'prod'.*http_(username|password)"):
        AppConfig(
            _write_config(
                tmp_path,
                'http_url = "https://gerrit.example.com"\n' + credentials,
            )
        )


def test_http_password_is_not_disclosed_by_validation_error(tmp_path):
    secret = "uniquely-sensitive-token"

    with pytest.raises(ValueError) as error:
        AppConfig(
            _write_config(
                tmp_path,
                f'http_url = "https://gerrit.example.com"\nhttp_password = "{secret}"\n',
            )
        )

    assert secret not in str(error.value)


@pytest.mark.parametrize(
    "url",
    [
        "/gerrit",
        "ftp://gerrit.example.com",
        "https:///review",
        "https://user:password@gerrit.example.com",
        "https://gerrit.example.com?view=all",
        "https://gerrit.example.com#section",
        "https://gerrit.example.com/a",
        "https://gerrit.example.com/review/a/",
        "https://gerrit.example.com:invalid",
    ],
)
def test_invalid_http_urls_are_rejected(tmp_path, url):
    with pytest.raises(ValueError, match=r"instance 'prod'.*http_url"):
        AppConfig(_write_config(tmp_path, f'http_url = "{url}"\n'))


@pytest.mark.parametrize("raw_url", ["7", "true", '["https://gerrit.example.com"]'])
def test_http_url_must_be_a_string(tmp_path, raw_url):
    with pytest.raises(ValueError, match=r"instance 'prod'.*http_url"):
        AppConfig(_write_config(tmp_path, f"http_url = {raw_url}\n"))


@pytest.mark.parametrize("timeout", ["0", "-1", "true", '"slow"', '"5"'])
def test_http_timeout_must_be_a_positive_number(tmp_path, timeout):
    with pytest.raises(ValueError, match=r"instance 'prod'.*http_timeout"):
        AppConfig(
            _write_config(
                tmp_path,
                f'http_url = "https://gerrit.example.com"\nhttp_timeout = {timeout}\n',
            )
        )


@pytest.mark.parametrize("verify_tls", ['"true"', "1", "[]"])
def test_http_verify_tls_must_be_a_boolean(tmp_path, verify_tls):
    with pytest.raises(ValueError, match=r"instance 'prod'.*http_verify_tls"):
        AppConfig(
            _write_config(
                tmp_path,
                f'http_url = "https://gerrit.example.com"\nhttp_verify_tls = {verify_tls}\n',
            )
        )


def test_generated_config_documents_optional_http_settings(tmp_path):
    path = tmp_path / "config.toml"

    generate_example_config(path)

    generated = path.read_text(encoding="utf-8")
    assert '# http_url = "https://gerrit.example.com"' in generated
    assert '# http_username = "you"' in generated
    assert '# http_password = "secret-or-http-token"  # plaintext; protect this file' in generated
    assert "# http_timeout = 10" in generated
    assert "# http_verify_tls = true" in generated
