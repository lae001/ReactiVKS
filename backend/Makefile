.DEFAULT_GOAL := help
SHELL := /bin/bash

UV ?= uv
# Пакеты workspace: mypy проверяет их по одному – у каждого свой tests/conftest.py.
PACKAGES := $(wildcard libs/*) $(wildcard services/*)

.PHONY: help sync lint format type imports test test-unit cov check migrate migrate-auth migrate-meeting jwt-key run-auth

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
	@echo "==> scripts"
	@$(UV) run mypy scripts

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

# БД из deploy/docker-compose.dev.yml; для другой – make migrate AUTH_DATABASE_URL=… MEETING_DATABASE_URL=…
AUTH_DATABASE_URL ?= postgresql+asyncpg://auth_svc:auth-dev-password@localhost:5432/vks
MEETING_DATABASE_URL ?= postgresql+asyncpg://meeting_svc:meeting-dev-password@localhost:5432/vks

migrate: migrate-auth migrate-meeting ## Применить миграции всех сервисов к локальной БД

migrate-auth: ## Миграции auth-service (роль auth_svc)
	DATABASE_URL=$(AUTH_DATABASE_URL) $(UV) run alembic -c services/auth_service/alembic.ini upgrade head

migrate-meeting: ## Миграции meeting-service (роль meeting_svc)
	DATABASE_URL=$(MEETING_DATABASE_URL) $(UV) run alembic -c services/meeting_service/alembic.ini upgrade head

jwt-key: ## Ключ подписи JWT для локального запуска (secrets/jwt-private.pem, если его еще нет)
	@test -f secrets/jwt-private.pem || $(UV) run python scripts/gen_jwt_key.py --out secrets/jwt-private.pem

AUTH_ENV_FILE ?= services/auth_service/.env
AUTH_PORT ?= 8001

run-auth: ## auth-service на http://127.0.0.1:$(AUTH_PORT) (нужны make migrate, make jwt-key и .env)
	@test -f $(AUTH_ENV_FILE) || { echo "нет $(AUTH_ENV_FILE): cp services/auth_service/.env.example $(AUTH_ENV_FILE)"; exit 1; }
	$(UV) run --env-file $(AUTH_ENV_FILE) uvicorn auth_service.main:create_application --factory \
		--host 127.0.0.1 --port $(AUTH_PORT)
