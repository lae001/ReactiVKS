"""Разбор проверки порогов речи и жестов на живой камере (кнопка «Начать проверку» в демонстрации).

Файлы – ml/training/data/probe/<время>.json: по каждому кадру шаг сценария (silent, speak, nod, shake, turn, smile) и
сырые сигналы поведения. Скрипт сводит все файлы (разные люди, свет, камеры) и показывает:
- сработал ли каждый шаг так, как ожидалось (кивок пойман, при отвороте головы нет ложного «нет», …);
- распределение движения рта при молчании (silent, smile) и речи (speak) и порог, который их лучше всего разделяет
  (сейчас behavior.SPEECH_ON);
- размах поворота и наклона головы в шагах nod / shake / turn – чтобы сверить с NOD_DEG, SHAKE_DEG, MAX_GESTURE_DEG.

Запуск из ml/training:  uv run python scripts/analyze_probe.py [файлы…]   (по умолчанию – все из data/probe)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

STEPS = {
    "silent": ("Молчит", lambda r: not r["talk"] and not r["gesture"]),
    "speak": ("Говорит", lambda r: r["talk_share"] >= 0.5),
    "nod": ("Кивок", lambda r: "agree" in r["gestures"]),
    "shake": ("Покачивание", lambda r: "disagree" in r["gestures"]),
    "turn": ("Отворот головы", lambda r: "disagree" not in r["gestures"]),
    "smile": ("Улыбка молча", lambda r: r["talk_share"] <= 0.1),
}


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    talk = [r["speech"] in ("speaking", "side_talk") for r in rows]
    gestures = {str(r["agreement"]) for r in rows if r["agreement"] not in (None, "none")}
    yaw = [float(r["yaw"]) for r in rows if r["yaw"] is not None]  # type: ignore[arg-type]
    pitch = [float(r["pitch"]) for r in rows if r["pitch"] is not None]  # type: ignore[arg-type]
    return {
        "frames": len(rows),
        "talk_share": float(np.mean(talk)) if talk else 0.0,
        "talk": float(np.mean(talk)) > 0.1 if talk else False,
        "gesture": bool(gestures),
        "gestures": sorted(gestures),
        "yaw_range": round(max(yaw) - min(yaw), 1) if yaw else None,
        "pitch_range": round(max(pitch) - min(pitch), 1) if pitch else None,
    }


def best_threshold(quiet: np.ndarray, loud: np.ndarray) -> tuple[float, float]:
    """Порог движения рта с максимумом сбалансированной точности (среднее полноты «молчит» и «говорит»)."""
    best = (0.4, 0.0)
    for t in np.linspace(0.05, 0.95, 91):
        score = ((quiet < t).mean() + (loud >= t).mean()) / 2
        if score > best[1]:
            best = (float(t), float(score))
    return best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()
    files = [Path(f) for f in args.files] or sorted(Path("data/probe").glob("*.json"))
    if not files:
        raise SystemExit("Нет файлов проверки: запустите «Проверка порогов» в демонстрации (режим «Разработчик»).")

    passed: dict[str, list[bool]] = {s: [] for s in STEPS}
    mouth: dict[str, list[float]] = {s: [] for s in STEPS}
    for path in files:
        rows = [r for r in json.loads(path.read_text(encoding="utf-8")) if r.get("face")]
        print(f"\n{path.name}: {len(rows)} кадров с лицом")
        for step, (title, ok) in STEPS.items():
            part = [r for r in rows if r["step"] == step]
            if not part:
                continue
            summary = summarize(part)
            passed[step].append(bool(ok(summary)))
            mouth[step] += [float(r["mouth_activity"]) for r in part if r["mouth_activity"] is not None]
            print(
                f"  {'✓' if passed[step][-1] else '✗'} {title:15} речь {summary['talk_share']:.0%}, "
                f"жесты {summary['gestures'] or '—'}, "
                f"размах поворота {summary['yaw_range']}°, наклона {summary['pitch_range']}°"
            )

    print("\nИтог по всем файлам:")
    for step, (title, _) in STEPS.items():
        if passed[step]:
            print(f"  {title:15} пройдено {sum(passed[step])} из {len(passed[step])}")
    quiet = np.array(mouth["silent"] + mouth["smile"])
    loud = np.array(mouth["speak"])
    if len(quiet) and len(loud):
        threshold, score = best_threshold(quiet, loud)
        print(
            f"\nДвижение рта: молчание – медиана {np.median(quiet):.2f}, 95 % ≤ {np.quantile(quiet, 0.95):.2f}; "
            f"речь – медиана {np.median(loud):.2f}, 30 % ≤ {np.quantile(loud, 0.3):.2f}"
        )
        print(
            f"Лучший порог «говорит» (SPEECH_ON): {threshold:.2f}, сбалансированная точность {score:.0%} (сейчас 0,40)"
        )


if __name__ == "__main__":
    main()
