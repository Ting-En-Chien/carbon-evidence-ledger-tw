.PHONY: install test lint check version

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

check: lint test

version:
	python -m carbon_ledger --version
