run:
    uv run gcd

debug:
    LOG_LEVEL=DEBUG uv run gcd

ruff:
	ruff check . --fix
	ruff format .

test:
	uv run pytest

logs:
    tail -f log/ssh.log log/app.log log/plugin.log
