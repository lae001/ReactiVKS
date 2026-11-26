.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.NOTPARALLEL:

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
UV ?= uv
PNPM ?= pnpm
NODE_BIN ?=
export PATH := $(if $(NODE_BIN),$(NODE_BIN):)$(PATH)
STATE := $(ROOT)/.dev/full-stack
SERVICES := auth meeting analytics realtime ml frontend
SERVICE ?=
MONITORING ?= 1
START_TIMEOUT ?= 90
COMPOSE := docker compose -f "$(ROOT)/deploy/docker-compose.dev.yml" -f "$(ROOT)/deploy/docker-compose.monitoring.yml"
INFRA := postgres redis kafka kafka-init livekit
ifeq ($(MONITORING),1)
COMPOSE += --profile monitoring
endif

AUTH_ENV_FILE ?= $(or $(wildcard $(ROOT)/backend/services/auth_service/.env),services/auth_service/.env.example)
MEETING_ENV_FILE ?= $(or $(wildcard $(ROOT)/backend/services/meeting_service/.env),services/meeting_service/.env.example)
ANALYTICS_ENV_FILE ?= $(or $(wildcard $(ROOT)/backend/services/analytics_service/.env),services/analytics_service/.env.example)
REALTIME_ENV_FILE ?= $(or $(wildcard $(ROOT)/backend/services/realtime_service/.env),services/realtime_service/.env.example)
# Локальные значения LiveKit должны совпадать с deploy/.env и env-файлом meeting-service.
LIVEKIT_URL ?= ws://localhost:7880
LIVEKIT_API_KEY ?= devkey
LIVEKIT_API_SECRET ?= dev-secret-change-me-0123456789abcdef
ML_KAFKA_BOOTSTRAP ?= localhost:9092

.PHONY: help check-tools setup sync models infra infra-stop infra-logs up down restart start stop status health logs \
	migrate jwt-key run-auth run-meeting run-analytics run-realtime run-ml run-frontend test test-unit lint check urls

help: ## Все команды; первый запуск: make setup, затем make up
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-18s %s\n", $$1, $$2}' "$(ROOT)/Makefile"
	@printf '\nSERVICE=auth|meeting|analytics|realtime|ml|frontend; MONITORING=0 — без мониторинга.\n'
	@printf 'NODE_BIN=/путь/к/node/bin — каталог Node >=22.18, если текущая версия устарела.\n'

check-tools: ## Проверить инструменты и версию Node
	@for tool in $(UV) $(PNPM) node docker curl setsid lsof; do command -v "$$tool" >/dev/null || { printf 'Не найден %s\n' "$$tool"; exit 1; }; done
	@node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && minor < 18)) { console.error("Нужен Node >=22.18; используйте NODE_BIN=/путь/к/bin"); process.exit(1); }'
	@$(COMPOSE) version >/dev/null

setup: check-tools sync models infra migrate jwt-key ## Подготовить зависимости, модели, инфраструктуру, БД и JWT

sync: ## Установить зависимости по lock-файлам
	cd "$(ROOT)/backend" && $(UV) sync --locked
	cd "$(ROOT)/ml/emotion_service" && $(UV) sync --locked --extra agent
	cd "$(ROOT)/frontend" && $(PNPM) install --frozen-lockfile

models: ## Скачать недостающие модели (SHA-256 проверяется при скачивании)
	@cd "$(ROOT)/ml/models"; \
	for model in emotion/emotion-efficientnetb0-v1.2.0.onnx emotion-robust/emotion-efficientnetb0-v1.3.0.onnx \
		attributes/attributes-mobilenetv3-v1.0.0.onnx yunet/face_detection_yunet_2023mar.onnx \
		mediapipe/face_landmarker.task mediapipe/blaze_face_short_range.tflite; do \
		if [[ ! -s "$$model" ]]; then sh fetch_models.sh; break; fi; \
	done

infra: ## Поднять PostgreSQL, Redis, Kafka, LiveKit и мониторинг
	$(COMPOSE) up -d --wait $(INFRA)
	@if [[ "$(MONITORING)" == 1 ]]; then $(COMPOSE) up -d --wait prometheus grafana kafka-exporter; fi

infra-stop: ## Остановить контейнеры, сохранив данные
	$(COMPOSE) --profile monitoring stop

infra-logs: ## Следить за журналами контейнеров
	$(COMPOSE) logs --tail=100 -f

migrate: ## Применить миграции backend
	$(MAKE) -C "$(ROOT)/backend" migrate UV="$(UV)"

jwt-key: ## Создать ключ JWT, если его еще нет
	$(MAKE) -C "$(ROOT)/backend" jwt-key UV="$(UV)"

# Каждый процесс запускается в своей группе: stop завершает и дочерние процессы uv/ML/pnpm.
define runtime
	port() { case "$$1" in auth) echo 8001;; meeting) echo 8002;; analytics) echo 8003;; realtime) echo 8080;; ml) echo 8081;; frontend) echo 5173;; esac; }; \
	valid() { case " $(SERVICES) " in *" $$1 "*) ;; *) printf 'Неизвестный SERVICE: %s\n' "$$1"; exit 1;; esac; }; \
	alive() { [[ -f "$(STATE)/$$1.pid" ]] && kill -0 -- "-$$(cat "$(STATE)/$$1.pid")" 2>/dev/null; }; \
	stop_service() { \
		if alive "$$1"; then \
			pid=$$(cat "$(STATE)/$$1.pid"); kill -TERM -- "-$$pid" 2>/dev/null || true; \
			for ((i=0; i<40; i++)); do kill -0 -- "-$$pid" 2>/dev/null || break; sleep 0.2; done; \
			kill -KILL -- "-$$pid" 2>/dev/null || true; \
		fi; \
		rm -f "$(STATE)/$$1.pid"; printf '%s остановлен\n' "$$1"; \
	}; \
	start_service() { \
		if alive "$$1"; then printf '%s уже запущен\n' "$$1"; return; fi; \
		p=$$(port "$$1"); \
		if lsof -iTCP:"$$p" -sTCP:LISTEN -t >/dev/null 2>&1; then \
			printf 'Порт %s занят внешним процессом. Сначала остановите прежний %s.\n' "$$p" "$$1"; return 1; \
		fi; \
		mkdir -p "$(STATE)"; \
		setsid $(MAKE) --no-print-directory -C "$(ROOT)" "run-$$1" >"$(STATE)/$$1.log" 2>&1 </dev/null & \
		pid=$$!; printf '%s\n' "$$pid" >"$(STATE)/$$1.pid"; \
		path=/ready; case "$$1" in ml|frontend) path=/;; esac; \
		for ((i=0; i<$(START_TIMEOUT); i++)); do \
			if curl -fsS --max-time 1 "http://127.0.0.1:$$p$$path" >/dev/null 2>&1; then printf '%s запущен (: %s)\n' "$$1" "$$p"; return; fi; \
			alive "$$1" || break; sleep 1; \
		done; \
		tail -n 30 "$(STATE)/$$1.log"; stop_service "$$1"; return 1; \
	};
endef

up: check-tools models infra migrate jwt-key ## Запустить весь настоящий стенд в фоне
	@$(runtime) \
	started=(); for service in $(SERVICES); do \
		if alive "$$service"; then printf '%s уже запущен\n' "$$service"; continue; fi; \
		if ! start_service "$$service"; then for running in "$${started[@]}"; do stop_service "$$running"; done; exit 1; fi; \
		started+=("$$service"); \
	done
	@$(MAKE) --no-print-directory urls

start: ## Запустить отдельный сервис в фоне: make start SERVICE=ml
	@$(runtime) valid "$(SERVICE)"; start_service "$(SERVICE)"

stop: ## Остановить отдельный сервис: make stop SERVICE=ml
	@$(runtime) valid "$(SERVICE)"; stop_service "$(SERVICE)"

down: ## Остановить весь управляемый стенд, сохранив БД и модели
	@$(runtime) for service in frontend ml realtime analytics meeting auth; do stop_service "$$service"; done
	@$(MAKE) --no-print-directory infra-stop

restart: ## Перезапустить весь стенд или один SERVICE
	@if [[ -n "$(SERVICE)" ]]; then \
		$(MAKE) --no-print-directory stop SERVICE="$(SERVICE)"; $(MAKE) --no-print-directory start SERVICE="$(SERVICE)"; \
	else $(MAKE) --no-print-directory down; $(MAKE) --no-print-directory up; fi

status: ## Показать процессы Makefile и контейнеры
	@$(runtime) for service in $(SERVICES); do \
		if alive "$$service"; then printf '%-12s работает (PID %s)\n' "$$service" "$$(cat "$(STATE)/$$service.pid")"; \
		else printf '%-12s остановлен\n' "$$service"; fi; done
	@$(COMPOSE) --profile monitoring ps

health: ## Проверить HTTP readiness backend, ML и фронтенд
	@$(runtime) failed=0; for service in $(SERVICES); do \
		path=/ready; case "$$service" in ml|frontend) path=/;; esac; \
		if curl -fsS --max-time 5 "http://127.0.0.1:$$(port "$$service")$$path" >/dev/null; then printf '%s: OK\n' "$$service"; \
		else printf '%s: недоступен\n' "$$service"; failed=1; fi; done; exit $$failed

logs: ## Следить за логами всех процессов или SERVICE=auth
	@if [[ -n "$(SERVICE)" ]]; then \
		case " $(SERVICES) " in *" $(SERVICE) "*) ;; *) printf 'Неизвестный SERVICE\n'; exit 1;; esac; \
		tail -n 100 -f "$(STATE)/$(SERVICE).log"; \
	else files=("$(STATE)"/*.log); [[ -f "$${files[0]}" ]] || { printf 'Нет журналов: make up\n'; exit 1; }; tail -n 30 -f "$${files[@]}"; fi

run-auth: ## Запустить auth в текущем терминале
run-meeting: ## Запустить meeting в текущем терминале
run-analytics: ## Запустить analytics в текущем терминале
run-realtime: ## Запустить realtime в текущем терминале
run-auth run-meeting run-analytics run-realtime:
	$(MAKE) -C "$(ROOT)/backend" $@ UV="$(UV)" \
		AUTH_ENV_FILE="$(AUTH_ENV_FILE)" MEETING_ENV_FILE="$(MEETING_ENV_FILE)" \
		ANALYTICS_ENV_FILE="$(ANALYTICS_ENV_FILE)" REALTIME_ENV_FILE="$(REALTIME_ENV_FILE)"

run-ml: ## Запустить настоящий ML-агент в текущем терминале
	cd "$(ROOT)/ml/emotion_service" && LIVEKIT_URL="$(LIVEKIT_URL)" LIVEKIT_API_KEY="$(LIVEKIT_API_KEY)" \
		LIVEKIT_API_SECRET="$(LIVEKIT_API_SECRET)" ML_KAFKA_BOOTSTRAP="$(ML_KAFKA_BOOTSTRAP)" \
		$(UV) run --no-sync emotion-agent start --drain-timeout 5

run-frontend: ## Запустить frontend в HTTP-режиме в текущем терминале
	cd "$(ROOT)/frontend" && VITE_API_MODE=http $(PNPM) dev --host 127.0.0.1 --port 5173 --strictPort

test: ## Все тесты backend, включая интеграционные
test-unit: ## Тесты backend без Docker
lint: ## Ruff и форматирование backend
check: ## Полная проверка backend: Ruff, mypy, импорты, тесты
test test-unit lint check:
	$(MAKE) -C "$(ROOT)/backend" $@ UV="$(UV)"

urls: ## Адреса для проверки в браузере
	@printf 'Frontend:   http://localhost:5173\nAdmin:      http://localhost:5173/admin\nAuth API:   http://localhost:8001/docs\nMeeting API:http://localhost:8002/docs\nAnalytics:  http://localhost:8003/docs\n'
	@if [[ "$(MONITORING)" == 1 ]]; then printf 'Grafana:    http://localhost:3000/d/reactivks\nPrometheus: http://localhost:9090\n'; fi
