# 026 - Gerrit HTTP connection configuration

## Problem

Gerrit instances currently describe only their SSH connection (`host`, `port`,
and `email`). Future Gerrit REST API features need an HTTP base URL,
authentication, timeout, and TLS policy, but there is no typed place to store
those settings.

The existing `ci_errors` plugin also uses HTTP, but it calls a separate service
with plugin-specific configuration. Its request settings are unrelated to the
Gerrit REST API and must not be changed by this feature.

## Scope

Add optional Gerrit HTTP connection settings to each `[instance.<name>]` TOML
section. Parse and validate the settings at startup and expose them as one typed,
immutable value on `GerritInstance`.

This is configuration infrastructure only. It does not create an HTTP client,
send requests, test connectivity, or migrate existing SSH operations to REST.

## Configuration surface

Each Gerrit instance may define these flat keys:

| Key | Type | Required | Default | Meaning |
|---|---|---:|---|---|
| `http_url` | string | Yes, to enable HTTP | None | Gerrit base URL, including any reverse-proxy path. |
| `http_username` | string | No | None | Username for HTTP basic authentication. |
| `http_password` | string | No | None | Password or HTTP token for HTTP basic authentication. |
| `http_timeout` | number | No | `10.0` | Request timeout in seconds for a future HTTP client. |
| `http_verify_tls` | boolean | No | `true` | Whether a future HTTP client verifies TLS certificates. |

`http_url` opts an instance into Gerrit HTTP support. If no `http_*` keys are
present, the instance remains SSH-only and its runtime HTTP configuration is
`None`.

### SSH-only instance

```toml
[instance.internal]
host = "gerrit-ssh.example.com"
port = 29418
```

### Anonymous HTTP

```toml
[instance.public]
host = "gerrit.example.org"
port = 29418
http_url = "https://gerrit.example.org"
http_timeout = 15
http_verify_tls = true
```

### HTTP basic authentication

```toml
[instance.internal]
host = "gerrit-ssh.example.com"
port = 29418
http_url = "https://review.example.com/gerrit"
http_username = "jdoe"
http_password = "secret-or-http-token"
http_timeout = 10
http_verify_tls = true
```

`http_password` is stored as plaintext in `config.toml`. Users are responsible
for restricting access to that file. The value must never be logged, displayed,
or included in an object's representation or validation error.

## URL semantics

`http_url` is the external base URL of the Gerrit installation:

- It must be an absolute `http://` or `https://` URL with a non-empty host.
- It may include a port and a reverse-proxy path.
- It must not contain embedded credentials, a query string, or a fragment.
- All trailing slashes are removed from the path during parsing so consumers
  receive a stable base URL. The root URL `https://gerrit.example.com/` therefore
  becomes `https://gerrit.example.com`.
- Its normalized path must not be `/a` or end in `/a`. That segment is Gerrit's
  authenticated-REST prefix, which a future HTTP client will add when using
  basic authentication.

Examples of valid values:

```text
https://gerrit.example.com
https://gerrit.example.com:8443
https://review.example.com/gerrit
```

## Authentication semantics

The presence of credentials determines the authentication mode; no separate
mode key is needed:

- Omitting both `http_username` and `http_password` configures anonymous access.
- Providing both configures HTTP basic authentication.
- Providing only one is invalid.
- Empty username or password strings are invalid.

The password may be a conventional password or a Gerrit HTTP password/token.
Environment variables, bearer tokens, credential commands, and secret stores are
outside this feature.

## Runtime model

Add an immutable HTTP configuration value in `gcd/core/models.py`:

```python
@dataclass(frozen=True)
class GerritHttpConfig:
    url: str
    username: str | None
    password: str | None = field(repr=False)
    timeout: float = 10.0
    verify_tls: bool = True
```

Extend `GerritInstance` with one optional field:

```python
@dataclass(frozen=True)
class GerritInstance:
    name: str
    host: str
    port: int
    email: str | None
    enabled_plugins: frozenset[str] = field(default_factory=frozenset)
    http: GerritHttpConfig | None = None
```

TOML uses flat `http_*` keys as requested, while runtime consumers receive a
cohesive value object. Consumers can determine support with
`instance.http is not None` and do not need to know how TOML is parsed.

The password field uses `repr=False` so the generated dataclass representation
does not expose it. Code that reports configuration errors must refer to the
field name, not its value.

## Parsing and validation

`AppConfig._parse_instances()` parses the HTTP fields for each instance and
constructs `GerritHttpConfig` only when `http_url` is present.

Configuration loading fails with a field-specific `ValueError` in these cases:

1. Any of `http_username`, `http_password`, `http_timeout`, or
   `http_verify_tls` is explicitly present without `http_url`.
2. `http_url` is not a string or does not satisfy the URL rules above, including
   the rule excluding Gerrit's `/a` authentication prefix.
3. Only one credential field is supplied.
4. A supplied credential is not a string or is empty.
5. `http_timeout` is not a number or is less than or equal to zero. TOML booleans
   are not accepted as numbers.
6. `http_verify_tls` is not a TOML boolean.

Defaults are applied only after the presence and type checks:

```text
http_timeout = 10.0
http_verify_tls = true
```

Validation happens during normal `AppConfig` loading and reload. A bad HTTP
configuration follows the existing configuration error path; it is not silently
ignored and does not fall back to SSH-only mode.

## Generated example configuration

`generate_example_config()` adds commented HTTP fields to the sample instance:

```toml
# [instance.test]
# host = "localhost"
# port = 22
# email = "you@example.com"
# plugins_enabled = []
# http_url = "https://gerrit.example.com"
# http_username = "you"
# http_password = "secret-or-http-token"  # plaintext; protect this file
# http_timeout = 10
# http_verify_tls = true
```

The HTTP fields are optional and commented, so generated configurations retain
their current SSH-only behavior.

## Error handling and secrecy

- Errors identify the instance and invalid field where practical.
- Errors involving `http_password` never contain the supplied value.
- `repr(GerritHttpConfig)` and `repr(GerritInstance)` never contain the password.
- No connection attempt is made during validation, so a syntactically valid but
  unreachable URL remains valid configuration.
- Disabling TLS verification is accepted when explicitly configured. This
  feature does not emit a runtime warning because it does not make requests; the
  generated example keeps the safe `true` default.

## Tests

Add focused configuration tests covering:

1. An existing SSH-only instance parses unchanged and has `http is None`.
2. `http_url` alone creates anonymous HTTP configuration with default timeout
   and TLS verification.
3. All HTTP fields parse into the expected typed values.
4. A reverse-proxy path is preserved and a trailing slash is removed.
5. Valid `http` and `https` URLs, optional ports, and paths are accepted.
6. Relative URLs, unsupported schemes, missing hosts, embedded credentials,
   queries, fragments, and URLs ending in Gerrit's `/a` prefix are rejected.
7. Every non-URL `http_*` key is rejected when `http_url` is absent.
8. Partial, empty, and non-string credentials are rejected.
9. Zero, negative, boolean, and non-numeric timeouts are rejected.
10. Non-boolean `http_verify_tls` values are rejected rather than coerced.
11. Password values do not appear in object representations or validation
    errors.
12. The generated example includes all optional HTTP keys as comments.

No HTTP mocking or network integration tests are needed because this feature
does not perform I/O.

## Files changed

| File | Change |
|---|---|
| `gcd/core/models.py` | Add `GerritHttpConfig` and optional `GerritInstance.http`. |
| `gcd/core/config/__init__.py` | Parse, validate, normalize, and generate examples for `http_*` settings. |
| `tests/test_selection_and_config.py` or a focused config test module | Cover valid settings, defaults, invalid settings, and secret handling. |

## Compatibility

- Existing config files remain valid without changes.
- SSH remains required by the current application and continues to use `host`
  and `port` independently of HTTP settings.
- HTTP settings are per instance; there are no app-wide defaults in `[config]`.
- Config reload replaces each instance's HTTP value together with its other
  parsed settings.
- Plugin configuration parsing is unchanged.

## Out of scope

- Creating a Gerrit REST API client or issuing any HTTP request.
- Connectivity or authentication checks at startup.
- Replacing Gerrit SSH queries or review operations with REST calls.
- Retries, proxies, connection pools, custom CA bundles, client certificates,
  bearer tokens, or external secret providers.
- Environment-variable expansion in TOML values.
- Changing the `ci_errors` plugin, its URL/API key configuration, or its
  hard-coded timeout.
