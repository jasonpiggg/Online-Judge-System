"""Build the Chinese report from Markdown and unaltered browser screenshots."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/experiment-report.md"
OUTPUT = ROOT / "output/pdf/atelier-oj-experiment-report.pdf"
WIDTH = 174 * mm
INK = colors.HexColor("#182B45")
BLUE = colors.HexColor("#3563E9")
MUTED = colors.HexColor("#66758A")
FONT = next(
    (
        p
        for p in [
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ]
        if p.exists()
    ),
    None,
)
if FONT is None:
    raise RuntimeError("Install a Chinese TrueType font: SimHei or WenQuanYi Zen Hei")
pdfmetrics.registerFont(TTFont("OJ", str(FONT)))
STYLES = {
    "title": ParagraphStyle(
        "title", fontName="OJ", fontSize=28, leading=38, textColor=INK, spaceAfter=18
    ),
    "h2": ParagraphStyle(
        "h2",
        fontName="OJ",
        fontSize=19,
        leading=26,
        textColor=INK,
        spaceAfter=14,
        keepWithNext=True,
    ),
    "h3": ParagraphStyle(
        "h3",
        fontName="OJ",
        fontSize=12,
        leading=18,
        textColor=BLUE,
        spaceBefore=8,
        spaceAfter=6,
        keepWithNext=True,
    ),
    "body": ParagraphStyle(
        "body", fontName="OJ", fontSize=9.3, leading=15, textColor=INK, wordWrap="CJK", spaceAfter=7
    ),
    "cell": ParagraphStyle(
        "cell", fontName="OJ", fontSize=8, leading=12, textColor=INK, wordWrap="CJK"
    ),
    "caption": ParagraphStyle(
        "caption",
        fontName="OJ",
        fontSize=8,
        leading=12,
        textColor=MUTED,
        alignment=1,
        spaceAfter=12,
    ),
}


def rich(value: str) -> str:
    value = html.escape(value.strip())
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    return re.sub(r"\[([^]]+)\]\(([^)]+)\)", r'<link href="\2" color="#3563E9">\1</link>', value)


def table(rows: list[list[str]]) -> Table:
    count = len(rows[0])
    widths = (
        [45 * mm, WIDTH - 45 * mm]
        if count == 2
        else [34 * mm, 15 * mm, WIDTH - 49 * mm]
        if count == 3
        else [WIDTH / count] * count
    )
    result = Table(
        [[Paragraph(rich(c), STYLES["cell"]) for c in row] for row in rows],
        colWidths=widths,
        repeatRows=1,
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0FE")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FB")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F2")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return result


def page(canvas, doc):
    canvas.saveState()
    canvas.resetTransforms()
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(18 * mm, 286 * mm, "ATELIER OJ / v1.1.0")
    canvas.setFont("OJ", 8)
    canvas.drawRightString(192 * mm, 286 * mm, "实验二：在线评测系统")
    canvas.setStrokeColor(colors.HexColor("#E2E8F2"))
    canvas.line(18 * mm, 282 * mm, 192 * mm, 282 * mm)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 11 * mm, "jasonpiggg · 2026-09-04")
    canvas.drawRightString(192 * mm, 11 * mm, str(doc.page))
    canvas.restoreState()


def build() -> None:
    story = []
    paragraph = []

    def flush():
        if paragraph:
            story.append(Paragraph(rich(" ".join(paragraph)), STYLES["body"]))
            paragraph.clear()

    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("# "):
            flush()
            story.extend([Spacer(1, 18 * mm), Paragraph(rich(line[2:]), STYLES["title"])])
        elif line.startswith("## "):
            flush()
            if story:
                story.append(PageBreak())
            story.extend([Spacer(1, 8 * mm), Paragraph(rich(line[3:]), STYLES["h2"])])
        elif line.startswith("### "):
            flush()
            story.append(Paragraph(rich(line[4:]), STYLES["h3"]))
        elif match := re.fullmatch(r"!\[([^]]*)\]\(([^)]+)\)", line):
            flush()
            visual = Image(str(SOURCE.parent / match[2]))
            scale = min(WIDTH / visual.imageWidth, 175 * mm / visual.imageHeight)
            visual.drawWidth, visual.drawHeight = (
                visual.imageWidth * scale,
                visual.imageHeight * scale,
            )
            story.append(
                KeepTogether(
                    [Spacer(1, 6 * mm), visual, Paragraph(rich(match[1]), STYLES["caption"])]
                )
            )
        elif line.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [x.strip() for x in lines[i].strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            story.extend([table(rows), Spacer(1, 10)])
            continue
        elif line.startswith("- "):
            flush()
            story.append(Paragraph("- " + rich(line[2:]), STYLES["body"]))
        elif line.strip():
            paragraph.append(line)
        else:
            flush()
        i += 1
    flush()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=28 * mm,
        bottomMargin=20 * mm,
        title="Atelier OJ 实验二报告 v1.1.0",
        author="jasonpiggg",
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="report-body",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates(PageTemplate(id="report", frames=[frame], onPageEnd=page))
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    build()
