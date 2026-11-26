"""CSV и PDF: пользовательские строки экранируются до формирования файла."""

import base64
import csv
import io
from collections.abc import Sequence
from html import escape
from typing import cast

from matplotlib.figure import Figure
from sqlalchemy import RowMapping
from weasyprint import HTML  # type: ignore[import-untyped]

from analytics_service.domain.report import DISCLAIMER
from analytics_service.domain.report_jobs import ReportView
from vks_contracts.ml_events import EMOTIONS


def render_csv(rows: Sequence[RowMapping]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        ["ts", "participant_id", "display_name", "samples", "face_samples", *("p_" + label for label in EMOTIONS)]
    )
    for row in rows:
        values = list(row.values())
        name = str(values[2])
        values[2] = "'" + name if name.lstrip().startswith(("=", "+", "-", "@")) else name
        values[0] = row.ts.isoformat()
        writer.writerow(values)
    return output.getvalue().encode("utf-8-sig")


def render_pdf(report: ReportView) -> bytes:
    summary = report.summary or {}
    overall = cast(dict[str, object], summary.get("overall", {}))
    probabilities = cast(dict[str, float], overall.get("mean_probabilities", {}))
    participants = cast(list[dict[str, object]], summary.get("participants", []))
    figure = Figure(figsize=(7, 3), layout="constrained")
    axes = figure.subplots()
    axes.bar(EMOTIONS, [probabilities.get(label, 0) for label in EMOTIONS])
    axes.set_ylim(0, 1)
    axes.set_ylabel("Probability")
    image = io.BytesIO()
    figure.savefig(image, format="png", dpi=120)
    chart = base64.b64encode(image.getvalue()).decode("ascii")
    people = "".join(
        f"<tr><td>{escape(str(person['display_name']))}</td><td>{escape(str(person['analyzed_seconds']))}</td>"
        f"<td>{escape(str(person.get('dominant') or '—'))}</td></tr>"
        for person in participants
    )
    marks = "".join(f"<li>{escape(str(mark['ts']))}: {escape(str(mark['label']))}</li>" for mark in report.markers)
    html = f"""<html lang="ru"><meta charset="utf-8"><style>
    @page {{ size: A4; margin: 18mm }} body {{ font-family: sans-serif; font-size: 11pt }}
    img {{ width: 100% }} table {{ width: 100%; border-collapse: collapse }} td, th {{ padding: 5px;
    border-bottom: 1px solid #ddd }} tr {{ break-inside: avoid }}
    </style><h1>{escape(report.title)}</h1><p>{escape(str(report.started_at))} — {escape(str(report.ended_at))}</p>
    <p>{escape(DISCLAIMER)}</p><img src="data:image/png;base64,{chart}"><h2>Участники</h2>
    <table><tr><th>Имя</th><th>Секунд анализа</th><th>Эмоция</th></tr>{people}</table>
    <h2>Отметки</h2><ul>{marks}</ul></html>"""
    result: bytes = HTML(string=html).write_pdf()
    return result
