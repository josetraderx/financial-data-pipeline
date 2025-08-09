# Minimal Makefile for Python projects
PY=python3
VENV?=.venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
ACTIVATE=. $(VENV)/bin/activate

.PHONY: help setup install lint test format run docker-up docker-down

help:
	@echo "Targets: setup install lint test format run docker-up docker-down"

setup:
	$(PY) -m venv $(VENV)
	$(PIP) install --upgrade pip

install:
	@if [ -f requirements.txt ]; then \
		$(PIP) install -r requirements.txt; \
	else \
		$(PIP) install -e .; \
	fi

lint:
	$(PIP) install ruff black
	ruff check .
	black --check .

format:
	$(PIP) install black
	black .

test:
	$(PIP) install pytest
	pytest -q

run:
	$(PYTHON) -m pip show
	@echo "Define a run target specific to the repo (e.g., pipeline CLI)."

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v
