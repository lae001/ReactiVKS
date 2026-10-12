.DEFAULT_GOAL := help
SHELL := /bin/bash

UV ?= uv
# Пакеты workspace: mypy проверяет их по одному – у каждого свой tests/conftest.py.
PACKAGES := $(wildcard libs/*) $(wildcard services/*)

.PHONY: help sync lint format type imports test test-unit cov check migrate

help: ## Список команд
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

sync: ## Создать или обновить окружение по uv.lock
	$(UV) sync

lint: ## ruff: стиль и форматирование
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Привести код к стилю проекта
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

type: ## mypy --strict по каждому пакету
	@for package in $(PACKAGES); do \
		echo "==> $$package"; \
		$(UV) run mypy $$(ls -d $$package/src $$package/tests 2>/dev/null) || exit 1; \
	done

imports: ## import-linter: границы слоев
	$(UV) run lint-imports

# Код 5 – «тестов не найдено»: пакет без тестов не повод валить проверку.
test: ## Все тесты (интеграционным нужен Docker)
	@$(UV) run pytest; status=$$?; test $$status -eq 0 -o $$status -eq 5

test-unit: ## Только тесты без Docker
	@$(UV) run pytest -m "not integration"; status=$$?; test $$status -eq 0 -o $$status -eq 5

cov: ## Тесты с покрытием и порогом 60 %
	$(UV) run pytest --cov --cov-report=term --cov-fail-under=60

check: lint type imports test ## Все проверки, как в CI

# БД из deploy/docker-compose.dev.yml; для другой – make migrate AUTH_DATABASE_URL=…
AUTH_DATABASE_URL ?= postgresql+asyncpg://auth_svc:auth-dev-password@localhost:5432/vks

migrate: ## Применить миграции auth-service к локальной БД
	DATABASE_URL=$(AUTH_DATABASE_URL) $(UV) run alembic -c services/auth_service/alembic.ini upgrade head
