.PHONY: install dev test run lint clean

install:
	pip install -e .

dev:
	pip install -e '.[dev]'

test:
	pytest

run:
	python -m hoseki serve --config ./config.toml

clean:
	rm -rf build dist *.egg-info .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +