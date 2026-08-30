"""Server-side A4 emissions summary PDF (reportlab, embedded CJK fonts)."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from carbon_ledger.ui.emissions_report import (
    EmissionsReportModel,
    format_tco2e,
)
from carbon_ledger.ui.i18n import t

NAVY = HexColor("#0D2238")
NAVY_MID = HexColor("#16324F")
TEAL = HexColor("#0F8A83")
SLATE = HexColor("#334155")
SLATE_MUTED = HexColor("#64748B")
LINE = HexColor("#D8E1EA")
SURFACE = HexColor("#F4F7FA")
GREEN = HexColor("#21865A")
GREEN_BG = HexColor("#E7F6EE")
AMBER = HexColor("#B7791F")
AMBER_BG = HexColor("#FFF5DA")
WHITE = white

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONTS_READY = False


def register_report_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    regular = _FONT_DIR / "NotoSansTC-Regular.ttf"
    bold = _FONT_DIR / "NotoSansTC-Bold.ttf"
    if not regular.is_file() or not bold.is_file():
        raise FileNotFoundError(
            f"Embedded Noto Sans TC fonts missing in {_FONT_DIR}"
        )
    pdfmetrics.registerFont(TTFont("NotoSansTC", str(regular)))
    pdfmetrics.registerFont(TTFont("NotoSansTC-Bold", str(bold)))
    pdfmetrics.registerFontFamily(
        "NotoSansTC",
        normal="NotoSansTC",
        bold="NotoSansTC-Bold",
        italic="NotoSansTC",
        boldItalic="NotoSansTC-Bold",
    )
    _FONTS_READY = True


def _styles() -> dict[str, ParagraphStyle]:
    register_report_fonts()
    return {
        "kicker": ParagraphStyle(
            "kicker",
            fontName="NotoSansTC-Bold",
            fontSize=8,
            leading=11,
            textColor=TEAL,
            wordWrap="CJK",
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            fontName="NotoSansTC-Bold",
            fontSize=20,
            leading=28,
            textColor=WHITE,
            wordWrap="CJK",
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta",
            fontName="NotoSansTC",
            fontSize=9.5,
            leading=14,
            textColor=HexColor("#E2E8F0"),
            wordWrap="CJK",
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName="NotoSansTC-Bold",
            fontSize=13,
            leading=18,
            textColor=NAVY,
            spaceBefore=4,
            spaceAfter=8,
            wordWrap="CJK",
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="NotoSansTC-Bold",
            fontSize=10.5,
            leading=14,
            textColor=NAVY_MID,
            spaceBefore=2,
            spaceAfter=4,
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "body",
            fontName="NotoSansTC",
            fontSize=9,
            leading=13.5,
            textColor=SLATE,
            alignment=TA_JUSTIFY,
            wordWrap="CJK",
        ),
        "caption": ParagraphStyle(
            "caption",
            fontName="NotoSansTC",
            fontSize=8,
            leading=11.5,
            textColor=SLATE_MUTED,
            wordWrap="CJK",
        ),
        "th": ParagraphStyle(
            "th",
            fontName="NotoSansTC-Bold",
            fontSize=8,
            leading=11,
            textColor=WHITE,
            wordWrap="CJK",
        ),
        "td": ParagraphStyle(
            "td",
            fontName="NotoSansTC",
            fontSize=8,
            leading=11.5,
            textColor=SLATE,
            wordWrap="CJK",
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            fontName="NotoSansTC-Bold",
            fontSize=12,
            leading=16,
            textColor=NAVY,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            fontName="NotoSansTC",
            fontSize=7.5,
            leading=10,
            textColor=SLATE_MUTED,
            wordWrap="CJK",
        ),
        "badge": ParagraphStyle(
            "badge",
            fontName="NotoSansTC-Bold",
            fontSize=8,
            leading=11,
            textColor=NAVY,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName="NotoSansTC",
            fontSize=7.5,
            leading=10,
            textColor=SLATE_MUTED,
            wordWrap="CJK",
        ),
        "center_white": ParagraphStyle(
            "center_white",
            fontName="NotoSansTC",
            fontSize=9,
            leading=13,
            textColor=WHITE,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
    }


class _HRule(Flowable):
    def __init__(self, color: Color = LINE, thickness: float = 0.6) -> None:
        super().__init__()
        self.color = color
        self.thickness = thickness
        self.height = 6

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self) -> None:
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 3, self.width, 3)


class _StatusChip(Flowable):
    def __init__(self, label: str, *, complete: bool) -> None:
        super().__init__()
        self.label = label
        self.complete = complete
        self.width = 78 * mm
        self.height = 8 * mm

    def wrap(self, availWidth, availHeight):
        self.width = min(78 * mm, availWidth)
        return self.width, self.height

    def draw(self) -> None:
        fill = GREEN_BG if self.complete else AMBER_BG
        stroke = GREEN if self.complete else AMBER
        self.canv.setFillColor(fill)
        self.canv.setStrokeColor(stroke)
        self.canv.setLineWidth(0.8)
        self.canv.roundRect(0, 0, self.width, self.height, 3, fill=1, stroke=1)
        self.canv.setFillColor(stroke)
        self.canv.setFont("NotoSansTC-Bold", 8)
        self.canv.drawCentredString(self.width / 2, 2.4 * mm, self.label)


class _BarChart(Flowable):
    def __init__(self, rows: list[tuple[str, float, str]], *, title: str = "") -> None:
        super().__init__()
        self.rows = rows
        self.title = title
        self.height = 12 * mm + max(len(rows), 1) * 9 * mm

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self) -> None:
        canv = self.canv
        y = self.height - 4 * mm
        if self.title:
            canv.setFillColor(NAVY)
            canv.setFont("NotoSansTC-Bold", 8)
            canv.drawString(0, y, self.title)
            y -= 6 * mm
        max_value = max((value for _n, value, _l in self.rows), default=1.0) or 1.0
        bar_left = 42 * mm
        bar_width = max(self.width - bar_left - 28 * mm, 20 * mm)
        for index, (name, value, label) in enumerate(self.rows):
            fill = TEAL if index % 2 else NAVY
            canv.setFillColor(SLATE)
            canv.setFont("NotoSansTC", 7.5)
            canv.drawString(0, y, _clip(name, 18))
            length = bar_width * (value / max_value)
            canv.setFillColor(fill)
            canv.rect(bar_left, y - 1.2 * mm, length, 4.2 * mm, fill=1, stroke=0)
            canv.setStrokeColor(NAVY if index % 2 else TEAL)
            canv.setLineWidth(0.4)
            canv.rect(bar_left, y - 1.2 * mm, length, 4.2 * mm, fill=0, stroke=1)
            canv.setFillColor(NAVY)
            _draw_text_with_co2e_subscripts(
                canv,
                self.width,
                y,
                label,
                font="NotoSansTC",
                size=7.5,
                align="right",
            )
            y -= 9 * mm


def _clip(text: str, n: int) -> str:
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1] + "…"


def _fit_width(text: str, font: str, size: float, max_width: float) -> str:
    text = str(text or "")
    if pdfmetrics.stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "…"
    while text and pdfmetrics.stringWidth(text + ellipsis, font, size) > max_width:
        text = text[:-1]
    return (text + ellipsis) if text else ellipsis


_CO2E_UNIT_RE = re.compile(r"(tCO|kgCO|CO)(?:₂|2)(e)")


def _co2e_segments(text: str) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    last = 0
    for match in _CO2E_UNIT_RE.finditer(text):
        if match.start() > last:
            parts.append((text[last : match.start()], False))
        parts.append((match.group(1), False))
        parts.append(("2", True))
        parts.append((match.group(2), False))
        last = match.end()
    if last < len(text):
        parts.append((text[last:], False))
    if not parts:
        parts.append((text, False))
    return parts


def _co2e_text_width(text: str, font: str, size: float) -> float:
    sub_size = size * 0.62
    total = 0.0
    for segment, is_sub in _co2e_segments(text):
        total += pdfmetrics.stringWidth(
            segment, font, sub_size if is_sub else size
        )
    return total


def _draw_text_with_co2e_subscripts(
    canv,
    x: float,
    y: float,
    text: str,
    *,
    font: str,
    size: float,
    align: str = "left",
) -> None:
    """Draw tCO₂e with a true subscript 2 from Noto Sans TC ASCII glyphs."""
    sub_size = size * 0.62
    sub_drop = size * 0.22
    raw = str(text or "")
    width = _co2e_text_width(raw, font, size)
    if align == "right":
        cursor = x - width
    elif align == "center":
        cursor = x - width / 2
    else:
        cursor = x
    for segment, is_sub in _co2e_segments(raw):
        if not segment:
            continue
        if is_sub:
            canv.setFont(font, sub_size)
            canv.drawString(cursor, y - sub_drop, segment)
            cursor += pdfmetrics.stringWidth(segment, font, sub_size)
        else:
            canv.setFont(font, size)
            canv.drawString(cursor, y, segment)
            cursor += pdfmetrics.stringWidth(segment, font, size)
    canv.setFont(font, size)


def _markup_units(text: str) -> str:
    marked = _escape(str(text or ""))
    replacements = (
        ("kgCO₂e", "kgCO<sub>2</sub>e"),
        ("tCO₂e", "tCO<sub>2</sub>e"),
        ("CO₂e", "CO<sub>2</sub>e"),
        ("kgCO2e", "kgCO<sub>2</sub>e"),
        ("tCO2e", "tCO<sub>2</sub>e"),
        ("CO2e", "CO<sub>2</sub>e"),
    )
    for source, dest in replacements:
        marked = marked.replace(source, dest)
    return marked


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_markup_units(str(text or "")), style)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _status_colors(complete: bool) -> tuple[Color, Color]:
    return (GREEN, GREEN_BG) if complete else (AMBER, AMBER_BG)


def _section_table(headers: list[str], rows: list[list[str]], styles: dict) -> Table:
    head = [_p(cell, styles["th"]) for cell in headers]
    body = [[_p(cell, styles["td"]) for cell in row] for row in rows]
    data = [head, *body] if body else [head, [_p("—", styles["td"])] * len(headers)]
    table = Table(data, repeatRows=1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "NotoSansTC-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "NotoSansTC"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
    ]
    for index in range(1, len(data)):
        if index % 2 == 0:
            commands.append(("BACKGROUND", (0, index), (-1, index), SURFACE))
    table.setStyle(TableStyle(commands))
    return table


def _kpi_table(model: EmissionsReportModel, styles: dict) -> Table:
    lang = model.lang
    cards = [
        (t("report.kpi.total", lang), format_tco2e(model.total_tco2e, lang)),
        (t("dash.kpi.scope1", lang), format_tco2e(model.scope_1_tco2e, lang)),
        (model.scope_2_method, format_tco2e(model.scope_2_tco2e, lang)),
        (
            t("report.kpi.included", lang),
            t(
                "report.kpi.included_value",
                lang,
                included=model.included_rows,
                total=model.population_rows,
            ),
        ),
        (t("report.kpi.pending", lang), str(model.pending_rows)),
        (t("report.kpi.excluded", lang), str(model.excluded_rows)),
        (t("report.kpi.documents", lang), str(model.source_documents)),
        (t("report.kpi.status", lang), model.status_label),
    ]
    cells = []
    for label, value in cards:
        inner = Table(
            [[_p(value, styles["kpi_value"])], [_p(label, styles["kpi_label"])]],
            colWidths=[42 * mm],
        )
        inner.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (0, 0), 8),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                    ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                    ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                    ("LINEABOVE", (0, 0), (-1, 0), 2.2, TEAL),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        cells.append(inner)
    grid = [cells[0:4], cells[4:8]]
    table = Table(grid, colWidths=[45 * mm] * 4)
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _cover(model: EmissionsReportModel, styles: dict) -> list:
    lang = model.lang
    meta_rows = [
        [t("report.cover.company", lang), model.company_name],
        [t("report.cover.period", lang), model.reporting_period],
        [t("report.cover.coverage", lang), model.data_coverage_period],
        [t("report.cover.year", lang), model.reporting_year],
        [t("report.cover.status", lang), model.status_label],
        [t("report.cover.generated", lang), model.generated_at],
        [t("report.cover.version", lang), model.system_version],
    ]
    meta = Table(
        [
            [_p(label, styles["cover_meta"]), _p(value, styles["cover_meta"])]
            for label, value in meta_rows
        ],
        colWidths=[38 * mm, 120 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, HexColor("#35506A")),
            ]
        )
    )
    banner = Table(
        [
            [_p(t("report.cover.kicker", lang), styles["kicker"])],
            [_p(model.report_title, styles["cover_title"])],
            [Spacer(1, 4 * mm)],
            [meta],
        ],
        colWidths=[178 * mm],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 12 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12 * mm),
                ("TOPPADDING", (0, 0), (0, 0), 14 * mm),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 12 * mm),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    note = _p(t("report.cover.positioning", lang), styles["body"])
    return [
        banner,
        Spacer(1, 8 * mm),
        _StatusChip(model.status_label, complete=model.complete),
        Spacer(1, 6 * mm),
        note,
        Spacer(1, 4 * mm),
        _p(t("report.assume.ghg_protocol", lang), styles["caption"]),
        PageBreak(),
    ]


def _bullet_list(items: tuple[str, ...] | list[str], styles: dict) -> list:
    flow = []
    for item in items:
        flow.append(_p(f"• {item}", styles["body"]))
        flow.append(Spacer(1, 1.4 * mm))
    return flow


def _build_story(model: EmissionsReportModel, styles: dict) -> list:
    lang = model.lang
    story: list = []
    story.extend(_cover(model, styles))

    story.append(_p(t("report.section.summary", lang), styles["h1"]))
    story.append(_HRule(TEAL, 1.4))
    story.append(_kpi_table(model, styles))
    story.append(Spacer(1, 3 * mm))
    story.append(
        _section_table(
            [t("report.col.field", lang), t("report.col.value", lang)],
            [
                [t("report.cover.period", lang), model.reporting_period],
                [t("report.cover.coverage", lang), model.data_coverage_period],
            ],
            styles,
        )
    )
    if model.coverage_partial:
        story.append(Spacer(1, 2 * mm))
        story.append(_p(t("report.coverage.partial", lang), styles["caption"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_p(model.status_explanation, styles["body"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_p(model.scope3_note, styles["body"]))
    bars = []
    if model.scope_1_tco2e is not None:
        bars.append(
            (
                t("dash.kpi.scope1", lang),
                float(model.scope_1_tco2e),
                format_tco2e(model.scope_1_tco2e, lang),
            )
        )
    if model.scope_2_tco2e is not None:
        bars.append(
            (
                t("dash.kpi.scope2", lang),
                float(model.scope_2_tco2e),
                format_tco2e(model.scope_2_tco2e, lang),
            )
        )
    if bars:
        story.append(Spacer(1, 4 * mm))
        story.append(_BarChart(bars, title=t("report.chart.scope", lang)))
    if model.sources:
        share_rows = [
            (
                row.name,
                row.tco2e,
                f"{format_tco2e(row.tco2e, lang)}  {row.share:.0%}",
            )
            for row in model.sources
        ]
        story.append(Spacer(1, 3 * mm))
        story.append(_BarChart(share_rows, title=t("report.chart.sources", lang)))

    story.append(PageBreak())
    story.append(_p(t("report.section.applicability", lang), styles["h1"]))
    story.append(_HRule(TEAL, 1.4))
    if model.applicability:
        app_rows = [
            [row.title, row.status, row.timing or "—", row.reason]
            for row in model.applicability
        ]
        story.append(
            _section_table(
                [
                    t("report.col.item", lang),
                    t("report.col.status", lang),
                    t("report.col.timing", lang),
                    t("report.col.reason", lang),
                ],
                app_rows,
                styles,
            )
        )
    else:
        story.append(_p(t("report.applicability.not_completed", lang), styles["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(_p(model.applicability_disclaimer, styles["caption"]))

    story.append(Spacer(1, 6 * mm))
    story.append(_p(t("report.section.boundary", lang), styles["h1"]))
    story.append(_HRule(TEAL, 1.4))
    story.append(
        _section_table(
            [t("report.col.field", lang), t("report.col.value", lang)],
            [
                [t("report.boundary.entity", lang), model.entity_name],
                [t("report.cover.period", lang), model.reporting_period],
                [
                    t("report.boundary.entities", lang),
                    "、".join(model.entities_included)
                    if model.entities_included
                    else t("report.still_pending", lang),
                ],
                [
                    t("report.boundary.entities_pending", lang),
                    "；".join(model.entities_pending)
                    if model.entities_pending
                    else t("report.none", lang),
                ],
                [t("report.boundary.summary", lang), model.boundary_summary],
                [
                    t("report.boundary.sites", lang),
                    "、".join(model.sites_included)
                    if model.sites_included
                    else t("report.still_pending", lang),
                ],
                [
                    t("report.boundary.pending", lang),
                    "；".join(model.boundary_pending)
                    if model.boundary_pending
                    else t("report.none", lang),
                ],
            ],
            styles,
        )
    )
    if model.exclusions:
        story.append(Spacer(1, 3 * mm))
        story.append(_p(t("report.boundary.exclusions", lang), styles["h2"]))
        story.append(
            _section_table(
                [t("report.col.item", lang), t("report.col.reason", lang)],
                [[name, reason] for name, reason in model.exclusions],
                styles,
            )
        )

    story.append(PageBreak())
    story.append(_p(t("report.section.results", lang), styles["h1"]))
    story.append(_HRule(TEAL, 1.4))
    result_rows = [
        [t("dash.kpi.scope1", lang), format_tco2e(model.scope_1_tco2e, lang), ""],
        [model.scope_2_method, format_tco2e(model.scope_2_tco2e, lang), ""],
    ]
    if model.sources:
        result_rows = [
            [row.name, format_tco2e(row.tco2e, lang), f"{row.share:.1%}"]
            for row in model.sources
        ]
        result_rows.append(
            [
                t("report.kpi.total", lang),
                format_tco2e(model.total_tco2e, lang),
                "100%",
            ]
        )
    story.append(
        _section_table(
            [
                t("report.col.source", lang),
                t("report.col.tco2e", lang),
                t("report.col.share", lang),
            ],
            result_rows,
            styles,
        )
    )
    if model.site_rows:
        story.append(Spacer(1, 4 * mm))
        story.append(_p(t("report.section.sites", lang), styles["h2"]))
        story.append(
            _section_table(
                [
                    t("report.col.site", lang),
                    t("report.col.tco2e", lang),
                    t("report.col.share", lang),
                ],
                [
                    [row.name, format_tco2e(row.tco2e, lang), f"{row.share:.1%}"]
                    for row in model.site_rows
                ],
                styles,
            )
        )

    story.append(Spacer(1, 6 * mm))
    story.append(_p(t("report.section.methods", lang), styles["h1"]))
    story.append(_HRule(TEAL, 1.4))
    if model.methods:
        method_rows = []
        for row in model.methods:
            detail = (
                f"{row.method}；{t('report.col.factor', lang)} {row.factor_label} "
                f"{row.factor_unit}；{row.factor_source}（{row.factor_year}）"
            )
            if row.heating:
                detail += f"；{row.heating}"
            method_rows.append([row.activity_name, detail, str(row.usage_count)])
        story.append(
            _section_table(
                [
                    t("report.col.source", lang),
                    t("report.col.method", lang),
                    t("report.col.usage_count", lang),
                ],
                method_rows,
                styles,
            )
        )
    else:
        story.append(_p(t("report.not_provided", lang), styles["body"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_p(t("report.section.assumptions", lang), styles["h2"]))
    story.extend(_bullet_list(model.assumptions, styles))

    story.append(PageBreak())
    story.append(_p(t("report.section.quality", lang), styles["h1"]))
    story.append(_HRule(TEAL, 1.4))
    story.append(
        _section_table(
            [t("report.col.field", lang), t("report.col.value", lang)],
            [
                [t("report.cover.period", lang), model.reporting_period],
                [t("report.cover.coverage", lang), model.data_coverage_period],
            ],
            styles,
        )
    )
    if model.coverage_partial:
        story.append(Spacer(1, 2 * mm))
        story.append(_p(t("report.coverage.partial", lang), styles["caption"]))
    story.append(Spacer(1, 3 * mm))
    story.append(
        _section_table(
            [t("report.col.disposition", lang), t("report.col.count", lang)],
            [[label, str(count)] for label, count in model.quality_counts],
            styles,
        )
    )
    story.append(Spacer(1, 3 * mm))
    recon_key = (
        "report.quality.reconciled"
        if model.quality_reconciled
        else "report.quality.unreconciled"
    )
    story.append(_p(t(recon_key, lang), styles["body"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_p(t("report.quality.exclusion_note", lang), styles["caption"]))

    story.append(Spacer(1, 6 * mm))
    story.append(_p(t("report.section.limits", lang), styles["h1"]))
    story.append(_HRule(TEAL, 1.4))
    story.extend(_bullet_list(model.limitations, styles))
    if not model.complete:
        story.append(Spacer(1, 2 * mm))
        story.append(_p(t("report.limit.preliminary_banner", lang), styles["body"]))

    story.append(PageBreak())
    story.append(_p(t("report.section.appendix", lang), styles["h1"]))
    story.append(_HRule(TEAL, 1.4))
    if model.appendix_files:
        story.append(
            _section_table(
                [
                    t("report.col.file", lang),
                    t("report.col.sheet", lang),
                    t("report.col.rows", lang),
                ],
                [[row.name, row.sheet, str(row.rows)] for row in model.appendix_files],
                styles,
            )
        )
    else:
        story.append(_p(t("report.not_provided", lang), styles["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(_p(t("report.section.factor_list", lang), styles["h2"]))
    if model.methods:
        story.append(
            _section_table(
                [
                    t("report.col.source", lang),
                    t("report.col.factor", lang),
                    t("report.col.unit", lang),
                    t("report.col.factor_source", lang),
                    t("report.col.year", lang),
                    t("report.col.usage_count", lang),
                ],
                [
                    [
                        row.activity_name,
                        row.factor_label,
                        row.factor_unit,
                        row.factor_source,
                        row.factor_year,
                        str(row.usage_count),
                    ]
                    for row in model.methods
                ],
                styles,
            )
        )
    else:
        story.append(_p(t("report.not_provided", lang), styles["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(_p(t("report.section.pending_items", lang), styles["h2"]))
    if model.appendix_pending:
        story.extend(_bullet_list(model.appendix_pending, styles))
    else:
        story.append(_p(t("report.pending.none", lang), styles["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(
        _p(
            t("report.appendix.generated", lang, when=model.generated_at),
            styles["caption"],
        )
    )
    return story


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, model: EmissionsReportModel, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []
        self._model = model

    def showPage(self) -> None:  # type: ignore[override]
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:  # type: ignore[override]
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_chrome(total)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_chrome(self, total: int) -> None:
        model = self._model
        page = self._pageNumber
        stroke, fill = _status_colors(model.complete)
        self.setStrokeColor(LINE)
        self.setFillColor(NAVY)
        self.setFont("NotoSansTC", 7.5)
        if page > 1:
            self.line(MARGIN, PAGE_H - 12 * mm, PAGE_W - MARGIN, PAGE_H - 12 * mm)
            title = _fit_width(model.report_title, "NotoSansTC", 7.5, 92 * mm)
            company = _fit_width(
                model.company_name, "NotoSansTC", 7.5, 70 * mm
            )
            self.drawString(MARGIN, PAGE_H - 10 * mm, title)
            self.drawRightString(PAGE_W - MARGIN, PAGE_H - 10 * mm, company)
        self.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
        self.setFillColor(fill)
        self.setStrokeColor(stroke)
        chip_w = 48 * mm
        self.roundRect(MARGIN, 6.2 * mm, chip_w, 4.4 * mm, 1.6, fill=1, stroke=1)
        self.setFillColor(stroke)
        self.setFont("NotoSansTC-Bold", 6.5)
        label = (
            t("dash.result_preliminary", model.lang)
            if not model.complete
            else t("dash.coverage_complete", model.lang)
        )
        self.drawCentredString(MARGIN + chip_w / 2, 7.5 * mm, _clip(label, 22))
        self.setFillColor(SLATE_MUTED)
        self.setFont("NotoSansTC", 7)
        self.drawString(
            MARGIN + chip_w + 4 * mm,
            7.6 * mm,
            f"{model.generated_at}  ·  v{model.system_version}",
        )
        self.drawRightString(
            PAGE_W - MARGIN,
            7.6 * mm,
            f"{page} / {total}",
        )


def render_emissions_summary_pdf(model: EmissionsReportModel) -> bytes:
    """Render the customer emissions summary as an A4 PDF."""
    register_report_fonts()
    styles = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=model.report_title,
        author=model.company_name,
        creator="Carbon Evidence Ledger",
        subject=model.report_title,
        invariant=1,
    )
    story = _build_story(model, styles)
    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: _NumberedCanvas(
            *args, model=model, **kwargs
        ),
    )
    return buffer.getvalue()
