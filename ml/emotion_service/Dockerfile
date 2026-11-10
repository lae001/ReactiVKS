# Образ emotion-ml-service (CPU). Контекст – корень репозитория: сервису нужен пакет vks_contracts из backend/.
#   docker build -f ml/emotion_service/Dockerfile -t vks/emotion-ml-service .
# Модели не запекаются в образ: каталог ml/models монтируется в /models (fetch_models.sh + модель из Releases).
FROM ghcr.io/astral-sh/uv:0.11.0 AS uv

FROM python:3.12-slim

# mediapipe тянет opencv-contrib-python (не headless) – ему нужны libGL и glib.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_FROZEN=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/ml/emotion_service/.venv/bin:$PATH"

# Раскладка как в репозитории: uv.lock ссылается на ../../backend/libs/vks_contracts.
WORKDIR /app/ml/emotion_service
COPY backend/libs/vks_contracts /app/backend/libs/vks_contracts
COPY ml/emotion_service/pyproject.toml ml/emotion_service/uv.lock ./
RUN uv sync --no-dev --extra agent --no-install-project
COPY ml/emotion_service/src src
RUN uv sync --no-dev --extra agent

ENV ML_MODEL_CARD=/models/emotion/model_card.json \
    ML_DETECTOR_MODEL=/models/yunet/face_detection_yunet_2023mar.onnx \
    ML_FACE_MESH_MODEL=/models/mediapipe/face_landmarker.task \
    ML_ATTRIBUTES_CARD=/models/attributes/attributes_card.json

RUN useradd --system --uid 10001 --no-create-home vks
USER vks
# HTTP-сервер воркера LiveKit Agents (/ – проверка живости) – порт 8081 в режиме start.
EXPOSE 8081
CMD ["emotion-agent", "start"]
