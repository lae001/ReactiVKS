# ml/emotion_service – агент распознавания эмоций

Воркер LiveKit Agents `emotion-agent` ([ADR-007](../../docs/adr/ADR-007-ml-as-livekit-agent.md)): подключается к
встрече как служебный участник, подписывается только на камеры участников с `vks.consent = granted`, берет
2–5 кадров/с и публикует сглаженные вероятности 7 эмоций. Устройство – [docs/ml/emotion-ml-service.md](../../docs/ml/emotion-ml-service.md).

## Модули

| Модуль | Назначение |
|---|---|
| `preprocessing.py` | Общий препроцессинг: выравнивание по глазам, кроп 48×48 серое (тот же код в обучении) |
| `detection.py` | `FaceDetector` (порт) и `YuNetDetector` |
| `classifier.py` | `EmotionClassifier` (порт), `OnnxEmotionClassifier`, чтение `model_card.json` |
| `smoothing.py` | EMA вероятностей по участнику (α = 0,4), сброс после 3 с без лица |
| `sampling.py` | `FrameSampler` («последний кадр выигрывает»), `AdaptiveRate` (адаптивная частота тактов) |
| `pipeline.py` | Такт: детекция → кроп → пакетная классификация → сглаживание (без ввода-вывода) |
| `events.py` | Payload `emotion.sample` / `ml.status` и конверт по [docs/api/events.md](../../docs/api/events.md) |
| `sinks.py` | `ResultSink` (порт): журнал сейчас, Kafka – следующим спринтом |
| `room.py` | `RoomAnalyzer`: события комнаты LiveKit, согласие, чтение дорожек, такты |
| `agent.py` | Точка входа воркера (`prewarm` загружает модель, `entrypoint` – задание на комнату) |

Ядро (`preprocessing` … `events`) не зависит от LiveKit и тестируется без сети; `room.py` и `agent.py` требуют
extra `agent`.

## Запуск

```bash
cd ml/emotion_service
uv sync --extra agent
../models/fetch_models.sh   # детектор YuNet (запуск из ml/models)
export LIVEKIT_URL=ws://localhost:7880 LIVEKIT_API_KEY=devkey LIVEKIT_API_SECRET=secret
export ML_MODEL_CARD=../models/emotion/model_card.json
uv run emotion-agent start
```

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `ML_MODEL_CARD` | `../models/emotion/model_card.json` | Карточка модели; ONNX – рядом, имя в карточке |
| `ML_DETECTOR_MODEL` | `../models/yunet/face_detection_yunet_2023mar.onnx` | Детектор лиц |
| `ML_TARGET_FPS` / `ML_MIN_FPS` / `ML_MAX_FPS` | 3 / 2 / 5 | Частота тактов (целевая берется из metadata диспетчеризации) |
| `ML_EMA_ALPHA` | 0.4 | Коэффициент сглаживания |
| `ML_ONNX_THREADS` | 2 | Потоки ONNX Runtime на задание |
| `ML_MAX_SIDE` | 640 | Кадр уменьшается до этой стороны перед детекцией |
| `ML_LOAD_THRESHOLD` | 0.7 | Загрузка CPU, выше которой воркер не берет новые встречи |
| `ML_WORKER_ID` | имя хоста | `worker_id` в `ml.status` |

## Проверка на локальном LiveKit

```bash
livekit-server --dev                                   # ключи devkey / secret
uv run emotion-agent start                             # в другом терминале
uv run python scripts/e2e_livekit.py --image face.png --seconds 30
```

Скрипт создает комнату с двумя участниками (с согласием и без), диспетчеризует агента и на середине отзывает
согласие. Ожидаемый журнал агента: отсчеты `analyzing` только для участника с согласием ≈ 3 раза в секунду,
`no_consent` для второго, после отзыва – `no_consent` и прекращение анализа, `ml.status` каждые 5 с.

## Тесты

```bash
uv run pytest && uv run ruff check . && uv run mypy src
```

## Живая демонстрация на веб-камере

```bash
uv run python scripts/live_demo.py --card <каталог модели>/model_card.json
```

Открыть http://localhost:8765 и нажать «Включить камеру». Браузер отправляет кадры (уменьшенные до 640 px, как
средний слой simulcast) локальному серверу, сервер прогоняет их через тот же `EmotionPipeline`, что и агент.
На странице: рамка и опорные точки лица, кроп 48×48, который видит модель, сглаженные и сырые вероятности 7 эмоций,
динамика за минуту, задержки конвейера. Сервер слушает только 127.0.0.1, кадры не сохраняются.
