ruff:
	ruff check . --fix
	ruff format .

test:
	uv run pytest
