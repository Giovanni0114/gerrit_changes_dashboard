run:
    uv run gcd

debug:
    LOG_LEVEL=DEBUG uv run gcd

fix:
    uv run ruff check . --fix
    uv run ruff format

check:
    uv run ruff check .
    uv run ty check gcd

test:
    uv run pytest

logs:
    tail -f log/ssh.log log/app.log log/plugin.log
