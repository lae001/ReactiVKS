# Образ Python-сервиса из uv workspace (EMO-71). Один файл на все сервисы – пакет выбирается аргументом:
#   docker build --build-arg PACKAGE=meeting-service -t vks/meeting-service backend/
# Контекст – backend/: сервису нужны его пакет, vks_common и vks_contracts из того же workspace.
FROM ghcr.io/astral-sh/uv:0.11.0 AS uv

FROM python:3.12-slim
ARG PACKAGE

COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_FROZEN=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Сначала зависимости по uv.lock – слой пересобирается только при смене lock-файла.
COPY pyproject.toml uv.lock ./
COPY libs/vks_common/pyproject.toml libs/vks_common/pyproject.toml
COPY libs/vks_contracts/pyproject.toml libs/vks_contracts/pyproject.toml
COPY services/auth_service/pyproject.toml services/auth_service/pyproject.toml
COPY services/meeting_service/pyproject.toml services/meeting_service/pyproject.toml
RUN uv sync --no-dev --no-install-workspace --package "${PACKAGE}"

# Исходники ставятся редактируемо: сервис находит свой alembic.ini рядом с пакетом (settings.ALEMBIC_INI).
COPY libs libs
COPY services services
RUN uv sync --no-dev --package "${PACKAGE}"

# Без прав root: сервису нужны только чтение кода и сеть.
RUN useradd --system --uid 10001 --no-create-home vks
USER vks
