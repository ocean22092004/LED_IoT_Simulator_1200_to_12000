COMPOSE := docker compose
PYTHON := .venv/bin/python

.PHONY: install install-web up down logs test test-web build-web test-unit test-integration migrate seed seed-scale reset-db compose-config

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e '.[dev]'

install-web:
	npm --prefix web ci

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down --remove-orphans

logs:
	$(COMPOSE) logs -f

test:
	$(COMPOSE) run --rm api pytest backend/tests -m 'not docker' -q
	$(COMPOSE) run --rm gateway-sim pytest simulator/tests -q
	$(PYTHON) -m pytest backend/tests -m docker -q
	npm --prefix web test -- --run

test-web:
	npm --prefix web test -- --run
	npm --prefix web run lint
	npm --prefix web run typecheck

build-web:
	npm --prefix web run build

test-unit:
	$(PYTHON) -m pytest backend/tests simulator/tests -m 'not integration and not scenario and not docker' -q

test-integration:
	$(COMPOSE) run --rm api pytest backend/tests/integration -q

migrate:
	$(COMPOSE) run --rm api alembic upgrade head

seed:
	$(COMPOSE) run --rm api python -m backend.app.seed --locations 1200

seed-scale:
	$(COMPOSE) run --rm api python -m backend.app.seed --locations 12000

reset-db:
	$(COMPOSE) down --volumes --remove-orphans
	$(COMPOSE) up -d postgres mosquitto

compose-config:
	$(COMPOSE) config --quiet
