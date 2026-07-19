.PHONY: install test lint gate sync skill-install ci

install:
	python -m pip install -U pip
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check src/image2svg/__init__.py src/image2svg/__main__.py src/image2svg/cli.py src/image2svg/paths.py src/image2svg/convert src/image2svg/background src/image2svg/config src/image2svg/web tests scripts

sync:
	python scripts/sync-agent-skills.py

gate: sync
	python scripts/prepublish-check.py

skill-install:
	python skills/installer/install.py install

ci: lint test gate
	image2svg --help
