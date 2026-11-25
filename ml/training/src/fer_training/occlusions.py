"""Синтетические очки и борода на лицах FER-2013 (48×48, серое) – по 5 точкам YuNet.

Два применения (experiments.md, §9):
- **аугментация**: модель учится узнавать эмоцию, когда часть лица закрыта оправой, тонированными стеклами,
  усами или бородой – в FER-2013 таких лиц мало;
- **проверка устойчивости**: тест FER-2013 с наложенными очками / бородой в фиксированных вариантах
  (OCCLUSION_SETS) – одинаковый для всех моделей, поэтому сравнение честное.

Рисование идет в 4-кратном разрешении и уменьшается INTER_AREA – тонкая оправа не превращается в лесенку.
Геометрия задается через межглазное расстояние d и ось глаз: размеры масштабируются с лицом, наклон головы
учитывается.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Final

import cv2
import numpy as np

SS: Final[int] = 4  # суперсэмплинг

# Средние точки FER-2013 (глаз, глаз, нос, рот, рот) для изображений, где YuNet не нашел лицо.
TEMPLATE: Final[np.ndarray] = np.array(
    [[16.0, 19.5], [32.0, 19.5], [24.0, 27.5], [17.5, 35.0], [30.5, 35.0]], np.float32
)


def _geometry(points: np.ndarray) -> dict[str, np.ndarray | float]:
    eye_a, eye_b, nose, mouth_a, mouth_b = points.astype(np.float64)
    left, right = (eye_a, eye_b) if eye_a[0] <= eye_b[0] else (eye_b, eye_a)
    m_left, m_right = (mouth_a, mouth_b) if mouth_a[0] <= mouth_b[0] else (mouth_b, mouth_a)
    axis = right - left
    d = float(np.linalg.norm(axis)) or 16.0
    u = axis / d
    v = np.array([-u[1], u[0]])
    if np.dot((m_left + m_right) / 2 - (left + right) / 2, v) < 0:
        v = -v
    return {"left": left, "right": right, "nose": nose, "m_left": m_left, "m_right": m_right, "d": d, "u": u, "v": v}


def _pt(p: np.ndarray) -> tuple[int, int]:
    return int(round(p[0] * SS)), int(round(p[1] * SS))


def _blend(image: np.ndarray, layer: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    small_layer = cv2.resize(layer, image.shape[::-1], interpolation=cv2.INTER_AREA)
    small_alpha = cv2.resize(alpha, image.shape[::-1], interpolation=cv2.INTER_AREA)
    out = image.astype(np.float32) * (1 - small_alpha) + small_layer * small_alpha
    return np.clip(out, 0, 255).astype(np.uint8)


def add_glasses(image: np.ndarray, points: np.ndarray, rng: np.random.Generator, tinted: bool = False) -> np.ndarray:
    """Оправа (круглая или прямоугольная), перемычка, дужки; tinted – солнцезащитные стекла."""
    g = _geometry(points)
    d, u, v = float(g["d"]), np.asarray(g["u"]), np.asarray(g["v"])
    h, w = image.shape
    layer = np.zeros((h * SS, w * SS), np.float32)
    alpha = np.zeros_like(layer)
    rx, ry = d * rng.uniform(0.36, 0.46), d * rng.uniform(0.24, 0.32)
    thickness = max(1, int(round(d * rng.uniform(0.05, 0.1) * SS)))
    color = rng.uniform(10, 60) if rng.random() < 0.8 else rng.uniform(150, 210)  # темная или металлическая
    angle = float(np.degrees(np.arctan2(u[1], u[0])))
    lens_shift = v * d * rng.uniform(-0.02, 0.08)
    round_lenses = rng.random() < 0.5  # форма одна на обе линзы
    lenses = []
    for eye in (np.asarray(g["left"]), np.asarray(g["right"])):
        center = eye + lens_shift
        lenses.append(center)
        axes = (int(rx * SS), int(ry * SS))
        if tinted:
            cv2.ellipse(layer, _pt(center), axes, angle, 0, 360, rng.uniform(10, 40), -1)
            cv2.ellipse(alpha, _pt(center), axes, angle, 0, 360, rng.uniform(0.75, 0.95), -1)
        elif rng.random() < 0.3:  # блик на стекле
            glare = center - u * rx * 0.3 - v * ry * 0.3
            cv2.ellipse(layer, _pt(glare), (int(rx * 0.4 * SS), int(ry * 0.25 * SS)), angle - 25, 0, 360, 235, -1)
            cv2.ellipse(alpha, _pt(glare), (int(rx * 0.4 * SS), int(ry * 0.25 * SS)), angle - 25, 0, 360, 0.5, -1)
        if round_lenses:
            cv2.ellipse(layer, _pt(center), axes, angle, 0, 360, color, thickness)
            cv2.ellipse(alpha, _pt(center), axes, angle, 0, 360, 1.0, thickness)
        else:
            box = cv2.boxPoints(((center[0] * SS, center[1] * SS), (2 * rx * SS, 2 * ry * SS), angle)).astype(np.int32)
            cv2.polylines(layer, [box], True, color, thickness)
            cv2.polylines(alpha, [box], True, 1.0, thickness)
    inner = (lenses[0] + u * rx, lenses[1] - u * rx)
    outer = (lenses[0] - u * rx, lenses[1] + u * rx)
    cv2.line(layer, _pt(inner[0]), _pt(inner[1]), color, thickness)
    cv2.line(alpha, _pt(inner[0]), _pt(inner[1]), 1.0, thickness)
    for start, direction in ((outer[0], -u), (outer[1], u)):
        end = start + direction * d * 0.3
        cv2.line(layer, _pt(start), _pt(end), color, thickness)
        cv2.line(alpha, _pt(start), _pt(end), 1.0, thickness)
    return _blend(image, layer, alpha)


def add_beard(image: np.ndarray, points: np.ndarray, rng: np.random.Generator, style: str = "full") -> np.ndarray:
    """style: full – борода по линии челюсти с усами; stubble – щетина; goatee – эспаньолка; mustache – усы."""
    g = _geometry(points)
    d, u, v = float(g["d"]), np.asarray(g["u"]), np.asarray(g["v"])
    m_left, m_right, nose = np.asarray(g["m_left"]), np.asarray(g["m_right"]), np.asarray(g["nose"])
    mouth = (m_left + m_right) / 2
    eyes = (np.asarray(g["left"]) + np.asarray(g["right"])) / 2
    chin = mouth + v * float(np.dot(mouth - eyes, v)) * rng.uniform(0.55, 0.75)
    h, w = image.shape
    mask = np.zeros((h * SS, w * SS), np.uint8)

    def polygon(points_: list[np.ndarray]) -> None:
        cv2.fillPoly(mask, [np.array([_pt(p) for p in points_], np.int32)], 255)

    if style in ("full", "stubble"):
        polygon([
            m_left - u * d * 0.45 - v * d * 0.25, m_left - u * d * 0.5 + v * d * 0.35, chin - u * d * 0.3 + v * d * 0.2,
            chin + v * d * 0.25, chin + u * d * 0.3 + v * d * 0.2, m_right + u * d * 0.5 + v * d * 0.35,
            m_right + u * d * 0.45 - v * d * 0.25, nose + u * d * 0.3 + v * d * 0.12, nose - u * d * 0.3 + v * d * 0.12,
        ])  # fmt: skip
    if style in ("goatee", "mustache", "full"):
        polygon([nose - u * d * 0.3 + v * d * 0.1, nose + u * d * 0.3 + v * d * 0.1,
                 m_right + u * d * 0.1 - v * d * 0.05, m_left - u * d * 0.1 - v * d * 0.05])  # fmt: skip
    if style == "goatee":
        polygon([m_left + v * d * 0.1, m_right + v * d * 0.1, chin + u * d * 0.18 + v * d * 0.2,
                 chin - u * d * 0.18 + v * d * 0.2])  # fmt: skip
    # Рот остается открытым: борода не закрывает губы.
    axes = (int(np.linalg.norm(m_right - m_left) * 0.55 * SS), int(d * 0.1 * SS))
    angle = float(np.degrees(np.arctan2(u[1], u[0])))
    cv2.ellipse(mask, _pt(mouth + v * d * 0.02), axes, angle, 0, 360, 0, -1)
    soft = cv2.GaussianBlur(mask.astype(np.float32) / 255, (0, 0), SS * 0.6)
    noise = rng.normal(0, 1, soft.shape).astype(np.float32)
    if style == "stubble":
        layer = np.clip(rng.uniform(40, 80) + 25 * noise, 0, 255)
        strength = rng.uniform(0.25, 0.45)
    else:
        grain = cv2.GaussianBlur(noise, (0, 0), SS * 0.35)
        layer = np.clip(rng.uniform(25, 70) + 30 * grain, 0, 255)
        strength = rng.uniform(0.7, 0.95)
    return _blend(image, layer, soft * strength)


OcclusionFn = Callable[[np.ndarray, np.ndarray, np.random.Generator], np.ndarray]

# Фиксированные варианты тестовых наборов устойчивости.
OCCLUSION_SETS: Final[dict[str, OcclusionFn]] = {
    "glasses": lambda img, pts, rng: add_glasses(img, pts, rng, tinted=False),
    "sunglasses": lambda img, pts, rng: add_glasses(img, pts, rng, tinted=True),
    "beard": lambda img, pts, rng: add_beard(img, pts, rng, "full"),
    "stubble": lambda img, pts, rng: add_beard(img, pts, rng, "stubble"),
    "mustache_goatee": lambda img, pts, rng: add_beard(img, pts, rng, "goatee"),
    "glasses_beard": lambda img, pts, rng: add_beard(add_glasses(img, pts, rng), pts, rng, "full"),
}


def landmarks_or_template(points: np.ndarray | None) -> np.ndarray:
    if points is None or np.isnan(points).any():
        return TEMPLATE
    return points


def occlude_set(images: np.ndarray, points: np.ndarray | None, name: str, seed: int = 0) -> np.ndarray:
    """Тестовый набор с наложением: детерминирован (seed + индекс изображения)."""
    fn = OCCLUSION_SETS[name]
    out = np.empty_like(images)
    for i, image in enumerate(images):
        rng = np.random.default_rng(seed * 1_000_003 + i)
        out[i] = fn(image, landmarks_or_template(None if points is None else points[i]), rng)
    return out


class RandomOcclusion:
    """Аугментация: с вероятностью p очки (обычные или солнцезащитные) и/или борода одного из стилей."""

    def __init__(self, p_glasses: float = 0.2, p_beard: float = 0.2, seed: int | None = None) -> None:
        self.p_glasses = p_glasses
        self.p_beard = p_beard
        self.seed = seed
        self._rng: np.random.Generator | None = None
        self._pid = 0

    @property
    def rng(self) -> np.random.Generator:
        # Процессы DataLoader получают копию объекта: генератор создается в каждом процессе заново, иначе все
        # процессы рисовали бы одинаковые очки.
        pid = os.getpid()
        if self._rng is None or pid != self._pid:
            self._rng = np.random.default_rng(None if self.seed is None else self.seed + pid)
            self._pid = pid
        return self._rng

    def __call__(self, image: np.ndarray, points: np.ndarray | None) -> np.ndarray:
        pts = landmarks_or_template(points) + self.rng.normal(0, 0.4, (5, 2)).astype(np.float32)
        if self.rng.random() < self.p_glasses:
            image = add_glasses(image, pts, self.rng, tinted=self.rng.random() < 0.25)
        if self.rng.random() < self.p_beard:
            style = self.rng.choice(["full", "stubble", "goatee", "mustache"], p=[0.4, 0.25, 0.2, 0.15])
            image = add_beard(image, pts, self.rng, str(style))
        return image
