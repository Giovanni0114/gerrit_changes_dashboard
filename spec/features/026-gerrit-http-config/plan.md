# Gerrit HTTP Connection Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse optional per-instance Gerrit REST connection settings into a validated, immutable, secret-safe runtime model without making HTTP requests.

**Architecture:** Add `GerritHttpConfig` beside `GerritInstance`, then keep TOML-specific parsing and URL normalization in `gcd/core/config/__init__.py`. `GerritInstance.http` is `None` for existing SSH-only instances and contains the cohesive HTTP value for REST-enabled instances. A focused test module exercises the public `AppConfig` boundary rather than exposing parsing helpers as public API.

**Tech Stack:** Python 3.12+, stdlib `dataclasses`, `urllib.parse`, `tomllib`, pytest, Ruff.

---

## File Map

- Modify `gcd/core/models.py`: define immutable `GerritHttpConfig` and attach it to `GerritInstance`.
- Modify `gcd/core/config/__init__.py`: validate and normalize flat per-instance `http_*` settings and extend generated example configuration.
- Create `tests/test_http_config.py`: cover the runtime model, accepted configurations, defaults, normalization, rejection rules, and generated examples.
- Do not modify `gcd/plugins/ci_errors.py`: its separate service configuration and request behavior are explicitly out of scope.

## Task 1: Add the secret-safe HTTP runtime model

**Files:**
- Create: `tests/test_http_config.py`
- Modify: `gcd/core/models.py:27-38`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_http_config.py`:

```python
from __future__ import annotations

from gcd.core.models import GerritHttpConfig, GerritInstance


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
```

- [ ] **Step 2: Run the model tests and verify they fail**

Run:

```bash
uv run pytest tests/test_http_config.py -v
```

Expected: collection fails because `GerritHttpConfig` cannot be imported.

- [ ] **Step 3: Add the immutable HTTP model**

In `gcd/core/models.py`, replace the current `GerritInstance` declaration with:

```python
@dataclass(frozen=True)
class GerritHttpConfig:
    url: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    timeout: float = 10.0
    verify_tls: bool = True


@dataclass(frozen=True)
class GerritInstance:
    name: str
    host: str
    port: int
    email: str | None
    enabled_plugins: frozenset[str] = field(default_factory=frozenset)
    http: GerritHttpConfig | None = None

    def __post_init__(self) -> None:
        if self.email is None:
            object.__setattr__(self, "email", get_email_from_git_config())
```

Appending `http` preserves all existing positional `GerritInstance` construction.

- [ ] **Step 4: Run the model tests and verify they pass**

Run:

```bash
uv run pytest tests/test_http_config.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit the runtime model**

```bash
git add gcd/core/models.py tests/test_http_config.py
git commit -m "feat(config): add Gerrit HTTP connection model"
```

## Task 2: Parse valid HTTP configurations

**Files:**
- Modify: `tests/test_http_config.py`
- Modify: `gcd/core/config/__init__.py:1-8,110-126`

- [ ] **Step 1: Add a config writer and valid parsing tests**

Add `Path` and `AppConfig` to the import block at the top of
`tests/test_http_config.py`:

```python
from pathlib import Path

from gcd.core.config import AppConfig
from gcd.core.models import GerritHttpConfig, GerritInstance
```

Replace the earlier standalone `gcd.core.models` import with this grouped block,
then append the helper and tests:

```python
def _write_config(tmp_path: Path, instance_settings: str = "") -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        "[config]\n"
        "default_port = 22\n"
        "\n"
        "[instance.prod]\n"
        'host = "gerrit-ssh.example.com"\n'
        f"{instance_settings}",
        encoding="utf-8",
    )
    return path


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
```

- [ ] **Step 2: Run the valid parsing tests and verify they fail**

Run:

```bash
uv run pytest tests/test_http_config.py -v
```

Expected: the four new parsing tests fail because `AppConfig` does not populate `GerritInstance.http`.

- [ ] **Step 3: Add HTTP parsing at the instance boundary**

In `gcd/core/config/__init__.py`, add the URL imports and model import:

```python
from urllib.parse import urlsplit, urlunsplit

from gcd.core.logs import app_logger
from gcd.core.models import GerritHttpConfig, GerritInstance
```

Add these constants below the existing default constants:

```python
DEFAULT_HTTP_TIMEOUT = 10.0
DEFAULT_HTTP_VERIFY_TLS = True
HTTP_CONFIG_KEYS = frozenset(
    {
        "http_url",
        "http_username",
        "http_password",
        "http_timeout",
        "http_verify_tls",
    }
)
```

Add this private parser immediately above `class AppConfig`:

```python
def _parse_http_config(instance_name: str, data: dict) -> GerritHttpConfig | None:
    if not HTTP_CONFIG_KEYS.intersection(data):
        return None

    raw_url = data.get("http_url")
    if raw_url is None:
        return None

    parsed = urlsplit(raw_url)
    normalized_path = parsed.path.rstrip("/")
    url = urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", ""))

    return GerritHttpConfig(
        url=url,
        username=data.get("http_username"),
        password=data.get("http_password"),
        timeout=float(data.get("http_timeout", DEFAULT_HTTP_TIMEOUT)),
        verify_tls=data.get("http_verify_tls", DEFAULT_HTTP_VERIFY_TLS),
    )
```

The `instance_name` parameter is intentionally introduced now because Task 3 uses it in validation errors.

In `_parse_instances()`, construct the HTTP value and pass all fields by keyword. Replace the current append call with:

```python
            http = _parse_http_config(name, ins)
            self.instances.append(
                GerritInstance(
                    name=name,
                    host=host,
                    port=port,
                    email=email,
                    enabled_plugins=enabled_plugins,
                    http=http,
                )
            )
```

- [ ] **Step 4: Run the HTTP tests and existing config tests**

Run:

```bash
uv run pytest tests/test_http_config.py tests/test_selection_and_config.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit valid HTTP parsing**

```bash
git add gcd/core/config/__init__.py tests/test_http_config.py
git commit -m "feat(config): parse Gerrit HTTP settings"
```

## Task 3: Enforce URL, authentication, timeout, and TLS rules

**Files:**
- Modify: `tests/test_http_config.py`
- Modify: `gcd/core/config/__init__.py`

- [ ] **Step 1: Add tests for dependent keys and authentication**

Add `import pytest` below the future import at the top of
`tests/test_http_config.py`, then append these tests:

```python
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
                'http_url = "https://gerrit.example.com"\n'
                f'http_password = "{secret}"\n',
            )
        )

    assert secret not in str(error.value)
```

- [ ] **Step 2: Add tests for URL validation**

Append to `tests/test_http_config.py`:

```python
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
```

- [ ] **Step 3: Add tests for timeout and TLS types**

Append to `tests/test_http_config.py`:

```python
@pytest.mark.parametrize("timeout", ["0", "-1", "true", '"slow"', '"5"'])
def test_http_timeout_must_be_a_positive_number(tmp_path, timeout):
    with pytest.raises(ValueError, match=r"instance 'prod'.*http_timeout"):
        AppConfig(
            _write_config(
                tmp_path,
                'http_url = "https://gerrit.example.com"\n'
                f"http_timeout = {timeout}\n",
            )
        )


@pytest.mark.parametrize("verify_tls", ['"true"', "1", "[]"])
def test_http_verify_tls_must_be_a_boolean(tmp_path, verify_tls):
    with pytest.raises(ValueError, match=r"instance 'prod'.*http_verify_tls"):
        AppConfig(
            _write_config(
                tmp_path,
                'http_url = "https://gerrit.example.com"\n'
                f"http_verify_tls = {verify_tls}\n",
            )
        )
```

- [ ] **Step 4: Run the validation tests and verify they fail**

Run:

```bash
uv run pytest tests/test_http_config.py -v
```

Expected: the new parametrized cases fail because strict validation is not implemented; valid parsing and model tests remain green.

- [ ] **Step 5: Replace the minimal parser with complete validation**

Replace `_parse_http_config()` in `gcd/core/config/__init__.py` with:

```python
def _parse_http_config(instance_name: str, data: dict) -> GerritHttpConfig | None:
    present_keys = HTTP_CONFIG_KEYS.intersection(data)
    if not present_keys:
        return None

    if "http_url" not in data:
        raise ValueError(f"Gerrit instance '{instance_name}' has HTTP options but no 'http_url'")

    raw_url = data["http_url"]
    if not isinstance(raw_url, str):
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_url': expected a string")

    try:
        parsed = urlsplit(raw_url)
        parsed.port
    except ValueError as ex:
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_url'") from ex

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            f"Gerrit instance '{instance_name}' has invalid 'http_url': expected an absolute HTTP(S) URL"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_url': embedded credentials are not allowed")
    if parsed.query or parsed.fragment:
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_url': query and fragment are not allowed")

    normalized_path = parsed.path.rstrip("/")
    if normalized_path == "/a" or normalized_path.endswith("/a"):
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_url': omit Gerrit's '/a' prefix")

    username_present = "http_username" in data
    password_present = "http_password" in data
    if username_present != password_present:
        missing = "http_password" if username_present else "http_username"
        raise ValueError(f"Gerrit instance '{instance_name}' must define '{missing}' for HTTP basic authentication")

    username = data.get("http_username")
    password = data.get("http_password")
    if username_present and (not isinstance(username, str) or not username):
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_username': expected a non-empty string")
    if password_present and (not isinstance(password, str) or not password):
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_password': expected a non-empty string")

    timeout = data.get("http_timeout", DEFAULT_HTTP_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not timeout > 0:
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_timeout': expected a positive number")

    verify_tls = data.get("http_verify_tls", DEFAULT_HTTP_VERIFY_TLS)
    if not isinstance(verify_tls, bool):
        raise ValueError(f"Gerrit instance '{instance_name}' has invalid 'http_verify_tls': expected a boolean")

    url = urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", ""))
    return GerritHttpConfig(
        url=url,
        username=username,
        password=password,
        timeout=float(timeout),
        verify_tls=verify_tls,
    )
```

No error includes the password value. `not timeout > 0` also rejects TOML `nan`, while the explicit boolean check avoids Python treating `True` as integer `1`.

- [ ] **Step 6: Run all HTTP and existing config tests**

Run:

```bash
uv run pytest tests/test_http_config.py tests/test_selection_and_config.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit strict validation**

```bash
git add gcd/core/config/__init__.py tests/test_http_config.py
git commit -m "feat(config): validate Gerrit HTTP settings"
```

## Task 4: Document settings in generated configuration and verify the feature

**Files:**
- Modify: `tests/test_http_config.py`
- Modify: `gcd/core/config/__init__.py:216-223`

- [ ] **Step 1: Add a failing generated-config test**

Append to `tests/test_http_config.py` and extend its config import:

```python
from gcd.core.config import AppConfig, generate_example_config


def test_generated_config_documents_optional_http_settings(tmp_path):
    path = tmp_path / "config.toml"

    generate_example_config(path)

    generated = path.read_text(encoding="utf-8")
    assert '# http_url = "https://gerrit.example.com"' in generated
    assert '# http_username = "you"' in generated
    assert '# http_password = "secret-or-http-token"  # plaintext; protect this file' in generated
    assert "# http_timeout = 10" in generated
    assert "# http_verify_tls = true" in generated
```

Replace the earlier `from gcd.core.config import AppConfig` line rather than retaining two imports from the same module.

- [ ] **Step 2: Run the generated-config test and verify it fails**

Run:

```bash
uv run pytest tests/test_http_config.py::test_generated_config_documents_optional_http_settings -v
```

Expected: FAIL because the generated sample does not contain `http_url` or the other HTTP settings.

- [ ] **Step 3: Add commented HTTP fields to the generated sample instance**

In `generate_example_config()`, extend the final `lines += [...]` block to:

```python
    lines += [
        "",
        "# [instance.test]",
        '# host = "localhost"',
        "# port = 22",
        '# email = "you@example.com"',
        "# plugins_enabled = []",
        '# http_url = "https://gerrit.example.com"',
        '# http_username = "you"',
        '# http_password = "secret-or-http-token"  # plaintext; protect this file',
        "# http_timeout = 10",
        "# http_verify_tls = true",
    ]
```

- [ ] **Step 4: Run the focused test suite**

Run:

```bash
uv run pytest tests/test_http_config.py tests/test_selection_and_config.py -v
```

Expected: all focused tests pass.

- [ ] **Step 5: Run formatting and static checks**

Run:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
```

Expected: final Ruff check exits 0 with no diagnostics. Review Ruff's edits before staging.

- [ ] **Step 6: Run the complete test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass with no network access.

- [ ] **Step 7: Verify scope and inspect the final diff**

Run:

```bash
git status --short
git diff --check
git diff -- gcd/core/models.py gcd/core/config/__init__.py tests/test_http_config.py
```

Expected: only the model, config parser/generator, and focused tests are changed; `git diff --check` emits no output; `gcd/plugins/ci_errors.py` is untouched.

- [ ] **Step 8: Commit generated documentation and final verification changes**

```bash
git add gcd/core/config/__init__.py tests/test_http_config.py
git commit -m "docs(config): show Gerrit HTTP settings in sample"
```

Do not stage or commit the `pm/` worktree from the implementation branch. Its spec and plan are versioned separately on the `pm` branch.
