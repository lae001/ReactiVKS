# ml/training – обучение модели распознавания эмоций

Пакет `fer_training`: загрузка датасетов, разбиение, аугментации под условия ВКС, обучение, оценка, экспорт в ONNX.
Устройство и требования – [docs/ml/ml-model.md](../../docs/ml/ml-model.md), датасеты и лицензии –
[docs/ml/datasets.md](../../docs/ml/datasets.md), результаты – [experiments.md](experiments.md).

## Установка

Python 3.12, [uv](https://docs.astral.sh/uv/). PyTorch ставится из индекса CUDA 12.8 (поддерживает RTX 50xx; на
машине без GPU обучение идет на CPU – медленно, для экспериментов лучше Colab/Kaggle).

```bash
cd ml/training
uv sync
```

Общий препроцессинг лица импортируется из `ml/emotion_service` (path-зависимость `emotion-service`): обучение и
сервис используют один и тот же код.

## Данные

См. [data/README.md](data/README.md): FER-2013 скачивается тремя файлами parquet, затем

```bash
uv run fer-train prepare          # кеш data/fer2013/fer2013.npz + распределение классов
```

## Команды

| Команда | Что делает |
|---|---|
| `fer-train train --config configs/<x>.yaml [ключ=значение …]` | Обучение; результат – `runs/<name>/<время>/` |
| `fer-train sweep --config … --grid train.lr=[3e-4,1e-3] train.balance=[none,sampler]` | Перебор сетки гиперпараметров |
| `fer-train export --checkpoint runs/…/best.pt --version 1.0.0 [--out ../models/emotion]` | ONNX + проверка PyTorch ↔ ONNX Runtime + `model_card.json` |
| `fer-train bench --onnx …/emotion-*.onnx` | Задержка ONNX Runtime на CPU, мс/лицо → `latency.json` |
| `fer-train report runs/<name>/<время> …` | Строки таблицы для `experiments.md` |
| `uv run python scripts/bench_face_detectors.py` | Сравнение детекторов YuNet и MediaPipe (EMO-44) |

Каталог запуска: `config.yaml` (полная конфигурация), `history.csv` (метрики по эпохам), `best.pt` (лучшая эпоха
по `train.select_metric` на валидации), `metrics.json` (val + все тестовые наборы), `confusion_*.png`.

## Конфигурации

| Файл | Эксперимент |
|---|---|
| `configs/baseline_cnn.yaml` | Базовая модель – простая CNN без предобучения |
| `configs/cmp_*.yaml` | Сравнение архитектур в одинаковых условиях |
| `configs/finetune_*.yaml` | Дообучение выбранной архитектуры (балансировка, гиперпараметры, + RAF-DB при наличии) |

Для RAF-DB достаточно указать `data.rafdb: data/rafdb`; для AffectNet и других датасетов в раскладке
`<root>/<split>/<класс>/*.jpg` – `data.folders: [data/affectnet]`.

## Colab / Kaggle

```python
!git clone <репозиторий> && cd ReactiVKS/ml/training && pip install -e ../emotion_service -e .
# данные: см. data/README.md
!fer-train train --config configs/cmp_resnet18.yaml train.num_workers=2
```

## Тесты и проверки

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
