from __future__ import annotations

import html
import io
import json
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.xpreformatted import XPreformatted


_FONT_NAME = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_MONO_FONT = "Courier"
_FONTS_INITIALIZED = False


def _init_fonts() -> None:
    global _FONT_NAME, _FONT_BOLD, _MONO_FONT, _FONTS_INITIALIZED
    if _FONTS_INITIALIZED:
        return

    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    ]
    bold_candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ]
    mono_candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSansMono.ttf"),
    ]

    regular = next((path for path in candidates if path.is_file()), None)
    bold = next((path for path in bold_candidates if path.is_file()), None)
    mono = next((path for path in mono_candidates if path.is_file()), None)

    if regular:
        pdfmetrics.registerFont(TTFont("RCADejaVu", str(regular)))
        _FONT_NAME = "RCADejaVu"
    if bold:
        pdfmetrics.registerFont(TTFont("RCADejaVuBold", str(bold)))
        _FONT_BOLD = "RCADejaVuBold"
    elif regular:
        _FONT_BOLD = _FONT_NAME
    if mono:
        pdfmetrics.registerFont(TTFont("RCADejaVuMono", str(mono)))
        _MONO_FONT = "RCADejaVuMono"

    _FONTS_INITIALIZED = True


def _safe_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if _FONT_NAME == "Helvetica":
        return text.encode("latin-1", "replace").decode("latin-1")
    return text


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _display_time(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return str(value)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "RcaTitle",
            parent=base["Title"],
            fontName=_FONT_BOLD,
            fontSize=20,
            leading=25,
            textColor=colors.HexColor("#111827"),
            alignment=TA_LEFT,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "RcaSubtitle",
            parent=base["BodyText"],
            fontName=_FONT_NAME,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
            spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "RcaSection",
            parent=base["Heading2"],
            fontName=_FONT_BOLD,
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=12,
            spaceAfter=7,
        ),
        "body": ParagraphStyle(
            "RcaBody",
            parent=base["BodyText"],
            fontName=_FONT_NAME,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#263244"),
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "RcaSmall",
            parent=base["BodyText"],
            fontName=_FONT_NAME,
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#64748B"),
        ),
        "mono": ParagraphStyle(
            "RcaMono",
            parent=base["Code"],
            fontName=_MONO_FONT,
            fontSize=6.2,
            leading=8,
            textColor=colors.HexColor("#0F172A"),
            backColor=colors.HexColor("#F8FAFC"),
            borderColor=colors.HexColor("#E2E8F0"),
            borderWidth=0.5,
            borderPadding=6,
            spaceBefore=4,
            spaceAfter=8,
        ),
    }


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(_safe_text(value)).replace("\n", "<br/>"), style)


def _json_block(value: Any, style: ParagraphStyle) -> XPreformatted:
    raw = _safe_text(_json_text(value))
    wrapped_lines: list[str] = []
    for line in raw.splitlines() or [""]:
        if len(line) <= 118:
            wrapped_lines.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        wrapped_lines.extend(
            textwrap.wrap(
                line,
                width=118,
                subsequent_indent=indent + "  ",
                replace_whitespace=False,
                drop_whitespace=False,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [line]
        )
    return XPreformatted("\n".join(wrapped_lines), style)


def _metadata_table(rows: list[tuple[str, Any]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [
            Paragraph(f"<b>{html.escape(_safe_text(label))}</b>", styles["small"]),
            Paragraph(html.escape(_safe_text(value)), styles["small"]),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[43 * mm, 132 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
            ]
        )
    )
    return table


def build_investigation_pdf(
    investigation,
    *,
    application_name: str | None,
    llm_history: list[Any],
) -> bytes:
    """Create one self-contained PDF with all persisted investigation data."""

    _init_fonts()
    styles = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"RCA Investigation #{investigation.id}",
        author="RCA Agent",
    )

    story: list[Any] = []
    story.append(_paragraph(f"RCA Investigation #{investigation.id}", styles["title"]))
    story.append(
        _paragraph(
            f"{application_name or 'Application'} · {investigation.status}",
            styles["subtitle"],
        )
    )

    story.append(
        _metadata_table(
            [
                ("Application", application_name or investigation.application_id or "—"),
                ("Trigger", investigation.trigger_type or "—"),
                ("Status", investigation.status or "—"),
                ("Created", _display_time(investigation.created_at)),
                ("Started", _display_time(investigation.started_at)),
                ("Finished", _display_time(investigation.finished_at)),
                ("LLM provider", investigation.llm_provider_type or "—"),
                ("LLM model", investigation.llm_model or "—"),
                ("Input tokens", int(investigation.llm_input_tokens or 0)),
                ("Output tokens", int(investigation.llm_output_tokens or 0)),
                ("Total tokens", int(investigation.llm_total_tokens or 0)),
                ("Token usage available", bool(investigation.llm_token_usage_available)),
                ("LLM history saved", bool(investigation.llm_history_enabled)),
                ("Alert ID", investigation.alert_id or "—"),
            ],
            styles,
        )
    )

    story.append(_paragraph("Investigation query", styles["section"]))
    story.append(_paragraph(investigation.query or "—", styles["body"]))

    if investigation.error:
        story.append(_paragraph("Investigation error", styles["section"]))
        story.append(_paragraph(investigation.error, styles["body"]))

    story.append(_paragraph("RCA result", styles["section"]))
    story.append(_json_block(investigation.rca_result or {}, styles["mono"]))

    story.append(_paragraph("Resolved scope / agent decisions", styles["section"]))
    story.append(_json_block(investigation.scope or {}, styles["mono"]))

    story.append(_paragraph("Collected evidence", styles["section"]))
    story.append(_json_block(investigation.evidence or [], styles["mono"]))

    story.append(PageBreak())
    story.append(_paragraph("LLM request / response history", styles["section"]))
    if not investigation.llm_history_enabled:
        story.append(_paragraph("History was not enabled for this investigation.", styles["body"]))
    elif not llm_history:
        story.append(_paragraph("No LLM interactions were stored.", styles["body"]))
    else:
        for item in llm_history:
            phase = getattr(item, "phase", None) or "LLM"
            sequence = getattr(item, "sequence", None)
            story.append(
                _paragraph(
                    f"#{sequence} · {phase}",
                    styles["section"],
                )
            )
            story.append(
                _metadata_table(
                    [
                        ("Provider", getattr(item, "provider_type", None) or "—"),
                        ("Model", getattr(item, "model", None) or "—"),
                        ("Input tokens", int(getattr(item, "input_tokens", 0) or 0)),
                        ("Output tokens", int(getattr(item, "output_tokens", 0) or 0)),
                        ("Total tokens", int(getattr(item, "total_tokens", 0) or 0)),
                        ("Duration ms", getattr(item, "duration_ms", None) or "—"),
                        ("Created", _display_time(getattr(item, "created_at", None))),
                    ],
                    styles,
                )
            )
            story.append(_paragraph("Request", styles["body"]))
            story.append(_json_block(getattr(item, "request_payload", None) or {}, styles["mono"]))
            story.append(_paragraph("Response", styles["body"]))
            story.append(_json_block(getattr(item, "response_payload", None) or {}, styles["mono"]))
            if getattr(item, "error", None):
                story.append(_paragraph("Error", styles["body"]))
                story.append(_paragraph(getattr(item, "error"), styles["body"]))
            story.append(Spacer(1, 6))

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont(_FONT_NAME, 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return buffer.getvalue()
