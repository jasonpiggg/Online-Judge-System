"""Build the verified Chinese experiment report PDF."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "experiment-report.md"
OUTPUT = ROOT / "output" / "pdf" / "atelier-oj-experiment-report.pdf"

INK = colors.HexColor("#142B3B")
PAPER = colors.HexColor("#F5F1E8")
ACID = colors.HexColor("#C8ED5B")
RUST = colors.HexColor("#C96743")
MUTED = colors.HexColor("#67747B")
GRID = colors.HexColor("#D9D5CB")
WHITE = colors.HexColor("#FFFDF7")

FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
)
FONT_PATH = next((path for path in FONT_CANDIDATES if path.exists()), None)
if FONT_PATH is None:
    raise RuntimeError("未找到可嵌入的中文字体，请安装 SimHei、WenQuanYi Zen Hei 或 Noto CJK")
pdfmetrics.registerFont(TTFont("OJText", str(FONT_PATH)))


def rich_text(value: str) -> str:
    """Escape source text and retain a restrained subset of Markdown."""
    escaped = html.escape(value.strip())
    escaped = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


class ArchitectureDiagram(Flowable):
    def __init__(self) -> None:
        super().__init__()
        self.width = 174 * mm
        self.height = 55 * mm

    def draw(self) -> None:
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(WHITE)
        canvas.roundRect(0, 0, self.width, self.height, 4 * mm, fill=1, stroke=0)
        boxes = [
            (5, 34, 31, 13, "BROWSER", "交互入口"),
            (44, 34, 34, 13, "STREAMLIT", "状态与展示"),
            (86, 34, 34, 13, "FASTAPI", "异步 API"),
        ]
        for x, y, w, h, title, sub in boxes:
            canvas.setFillColor(INK)
            canvas.roundRect(x * mm, y * mm, w * mm, h * mm, 2 * mm, fill=1, stroke=0)
            canvas.setFillColor(ACID)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawCentredString((x + w / 2) * mm, (y + 8.2) * mm, title)
            canvas.setFillColor(colors.white)
            canvas.setFont("OJText", 7)
            canvas.drawCentredString((x + w / 2) * mm, (y + 3.4) * mm, sub)
        canvas.setStrokeColor(MUTED)
        canvas.setLineWidth(1.2)
        for x1, x2 in ((36, 44), (78, 86)):
            canvas.line(x1 * mm, 40.5 * mm, x2 * mm, 40.5 * mm)
            canvas.line((x2 - 2) * mm, 42 * mm, x2 * mm, 40.5 * mm)
            canvas.line((x2 - 2) * mm, 39 * mm, x2 * mm, 40.5 * mm)
        stores = [
            (5, 8, 35, "JSON", "题目原子存储"),
            (47, 8, 35, "SQLITE", "状态与审计"),
            (89, 8, 35, "RUNNER", "受限子进程"),
            (131, 8, 35, "AI STREAM", "生成与验证"),
        ]
        for x, y, w, title, sub in stores:
            canvas.setFillColor(colors.HexColor("#E8E4D9"))
            canvas.roundRect(x * mm, y * mm, w * mm, 15 * mm, 2 * mm, fill=1, stroke=0)
            canvas.setFillColor(INK)
            canvas.setFont("Helvetica-Bold", 7.5)
            canvas.drawCentredString((x + w / 2) * mm, (y + 9.4) * mm, title)
            canvas.setFont("OJText", 7)
            canvas.drawCentredString((x + w / 2) * mm, (y + 4) * mm, sub)
        canvas.setStrokeColor(RUST)
        for target_x in (22.5, 64.5, 106.5, 148.5):
            canvas.line(103 * mm, 34 * mm, target_x * mm, 23 * mm)
        canvas.restoreState()


class InterfaceSnapshot(Flowable):
    """A compact reproduction of the browser-verified 639 px layout."""

    def __init__(self) -> None:
        super().__init__()
        self.width = 174 * mm
        self.height = 72 * mm

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.setFillColor(colors.HexColor("#E8E3D8"))
        c.roundRect(0, 0, self.width, self.height, 4 * mm, fill=1, stroke=0)
        c.setFillColor(INK)
        c.roundRect(4 * mm, 4 * mm, 42 * mm, 64 * mm, 3 * mm, fill=1, stroke=0)
        c.setFillColor(ACID)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(9 * mm, 58 * mm, "ATELIER OJ")
        c.setFont("OJText", 7)
        c.setFillColor(colors.white)
        c.drawString(9 * mm, 52 * mm, "程序设计实验室")
        for index, label in enumerate(("题目", "提交", "记录", "管理", "AI 命题")):
            y = 42 - index * 7
            if index == 0:
                c.setFillColor(ACID)
                c.roundRect(8 * mm, (y - 2) * mm, 30 * mm, 5.5 * mm, 1.3 * mm, fill=1, stroke=0)
                c.setFillColor(INK)
            else:
                c.setFillColor(colors.white)
            c.setFont("OJText", 7.5)
            c.drawString(11 * mm, y * mm, label)
        c.setFillColor(WHITE)
        c.roundRect(50 * mm, 4 * mm, 120 * mm, 64 * mm, 3 * mm, fill=1, stroke=0)
        c.setFillColor(RUST)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(57 * mm, 59 * mm, "PROBLEM / SUM_2")
        c.setFillColor(INK)
        c.setFont("OJText", 17)
        c.drawString(57 * mm, 49 * mm, "两数之和")
        c.setFont("OJText", 8)
        c.setFillColor(MUTED)
        c.drawString(57 * mm, 43 * mm, "读取两个整数，输出它们的和。")
        metrics = (
            (57, "时间限制", "1000 ms"),
            (96, "内存限制", "128 MB"),
            (135, "难度", "入门"),
        )
        for x, label, value in metrics:
            c.setFillColor(colors.HexColor("#ECE8DD"))
            c.roundRect(x * mm, 29 * mm, 31 * mm, 10 * mm, 1.5 * mm, fill=1, stroke=0)
            c.setFillColor(MUTED)
            c.setFont("OJText", 6.5)
            c.drawString((x + 3) * mm, 35 * mm, label)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString((x + 3) * mm, 31 * mm, value)
        c.setFillColor(INK)
        c.roundRect(57 * mm, 11 * mm, 42 * mm, 10 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(ACID)
        c.setFont("OJText", 8)
        c.drawCentredString(78 * mm, 14.8 * mm, "开始提交")
        c.setFillColor(MUTED)
        c.setFont("OJText", 6.5)
        c.drawRightString(164 * mm, 8 * mm, "管理员 · ROLE / ADMIN")
        c.restoreState()


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h2": ParagraphStyle(
            "H2", parent=base["Heading1"], fontName="OJText", fontSize=19,
            leading=25, textColor=INK, spaceAfter=7 * mm, keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading2"], fontName="OJText", fontSize=12.5,
            leading=18, textColor=RUST, spaceBefore=3 * mm, spaceAfter=2 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="OJText", fontSize=9.3,
            leading=16, textColor=INK, alignment=TA_LEFT, spaceAfter=2.3 * mm,
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["BodyText"], fontName="OJText", fontSize=8.8,
            leading=14.5, leftIndent=5 * mm, firstLineIndent=-3.5 * mm,
            textColor=INK, spaceAfter=1.2 * mm, wordWrap="CJK",
        ),
        "code": ParagraphStyle(
            "Code", parent=base["Code"], fontName="OJText", fontSize=8.2,
            leading=13, leftIndent=4 * mm, rightIndent=4 * mm, borderPadding=3 * mm,
            backColor=INK, textColor=colors.white, spaceBefore=1 * mm, spaceAfter=3 * mm,
        ),
        "caption": ParagraphStyle(
            "Caption", parent=base["BodyText"], fontName="OJText", fontSize=7.5,
            leading=11, textColor=MUTED, alignment=TA_CENTER, spaceBefore=1.5 * mm,
            spaceAfter=3 * mm,
        ),
        "cell": ParagraphStyle(
            "Cell", parent=base["BodyText"], fontName="OJText", fontSize=7.6,
            leading=11.2, textColor=INK, wordWrap="CJK",
        ),
        "cell_header": ParagraphStyle(
            "CellHeader", parent=base["BodyText"], fontName="OJText", fontSize=7.6,
            leading=11.2, textColor=colors.white, wordWrap="CJK",
        ),
    }


def make_table(rows: list[list[str]], style_map: dict[str, ParagraphStyle]) -> Table:
    width = 174 * mm
    columns = max(len(row) for row in rows)
    if columns == 2:
        widths = [45 * mm, width - 45 * mm]
    elif columns == 3:
        widths = (
            [45 * mm, 60 * mm, width - 105 * mm]
            if rows[0][1] == "结果"
            else [40 * mm, 18 * mm, width - 58 * mm]
        )
    else:
        widths = [width / columns] * columns
    data = [
        [
            Paragraph(rich_text(cell), style_map["cell_header" if index == 0 else "cell"])
            for cell in row
        ]
        for index, row in enumerate(rows)
    ]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "OJText"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PAPER]),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    return table


def parse_markdown(style_map: dict[str, ParagraphStyle]) -> list[Flowable]:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## 1."))
    lines = lines[start:]
    story: list[Flowable] = []
    paragraph: list[str] = []
    in_code = False
    code: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            story.append(Paragraph(rich_text(" ".join(paragraph)), style_map["body"]))
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            flush_paragraph()
            if in_code:
                code_text = "<br/>".join(html.escape(item) or " " for item in code)
                story.append(Paragraph(code_text, style_map["code"]))
                code.clear()
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code.append(line)
            index += 1
            continue
        if line.startswith("## "):
            flush_paragraph()
            if story:
                story.append(PageBreak())
            heading = line[3:]
            story.append(Paragraph(rich_text(heading), style_map["h2"]))
            if heading.startswith("2."):
                story.extend([
                    ArchitectureDiagram(),
                    Paragraph("图 1　系统组件与数据流", style_map["caption"]),
                ])
            index += 1
            continue
        if line.startswith("### "):
            flush_paragraph()
            heading = line[4:]
            story.append(Paragraph(rich_text(heading), style_map["h3"]))
            if heading.startswith("3.6"):
                story.extend([
                    InterfaceSnapshot(),
                    Paragraph("图 2　639 px 窄屏浏览器验收界面结构化重绘", style_map["caption"]),
                ])
            index += 1
            continue
        if line.startswith("| "):
            flush_paragraph()
            raw_rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                parts = lines[index].strip().strip("|").split("|")
                raw_rows.append([part.strip() for part in parts])
                index += 1
            rows = [
                row
                for row in raw_rows
                if not all(re.fullmatch(r":?-+:?", cell) for cell in row)
            ]
            story.extend([make_table(rows, style_map), Spacer(1, 3 * mm)])
            continue
        if line.startswith("- "):
            flush_paragraph()
            story.append(Paragraph("—　" + rich_text(line[2:]), style_map["bullet"]))
            index += 1
            continue
        if not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line.strip())
        index += 1
    flush_paragraph()
    return story


def first_page(canvas: Canvas, document: SimpleDocTemplate) -> None:
    del document
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(INK)
    canvas.rect(0, A4[1] - 12 * mm, A4[0], 12 * mm, fill=1, stroke=0)
    canvas.setFillColor(ACID)
    canvas.rect(0, 0, 16 * mm, A4[1], fill=1, stroke=0)
    canvas.restoreState()


def later_pages(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.3)
    for x in range(20, 201, 10):
        canvas.line(x * mm, 13 * mm, x * mm, 284 * mm)
    canvas.setFillColor(PAPER)
    canvas.rect(17 * mm, 13 * mm, 181 * mm, 271 * mm, fill=1, stroke=0)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(18 * mm, 288 * mm, "ATELIER OJ / EXPERIMENT 02")
    canvas.setFillColor(MUTED)
    canvas.setFont("OJText", 7)
    canvas.drawRightString(193 * mm, 288 * mm, "在线评测系统实验报告")
    canvas.setStrokeColor(INK)
    canvas.line(18 * mm, 285 * mm, 193 * mm, 285 * mm)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(18 * mm, 8 * mm, "JASONPIGGG / 2026")
    canvas.setFillColor(ACID)
    canvas.roundRect(179 * mm, 5.8 * mm, 14 * mm, 7 * mm, 1.5 * mm, fill=1, stroke=0)
    canvas.setFillColor(INK)
    canvas.drawCentredString(186 * mm, 8 * mm, f"{canvas.getPageNumber():02d}")
    canvas.restoreState()


def cover_story(style_map: dict[str, ParagraphStyle]) -> list[Flowable]:
    title = ParagraphStyle(
        "CoverTitle", fontName="OJText", fontSize=31, leading=42,
        textColor=INK, alignment=TA_LEFT,
    )
    kicker = ParagraphStyle(
        "CoverKicker", fontName="Helvetica-Bold", fontSize=9, leading=12,
        textColor=RUST, tracking=2,
    )
    meta = ParagraphStyle(
        "CoverMeta", parent=style_map["body"], fontSize=10, leading=19,
    )
    metadata = Table(
        [
            [
                Paragraph("姓名", style_map["cell"]),
                Paragraph("____________________", style_map["cell"]),
            ],
            [
                Paragraph("学号", style_map["cell"]),
                Paragraph("____________________", style_map["cell"]),
            ],
            [
                Paragraph("班级", style_map["cell"]),
                Paragraph("____________________", style_map["cell"]),
            ],
            [
                Paragraph("GitHub", style_map["cell"]),
                Paragraph("jasonpiggg / Online-Judge-System", style_map["cell"]),
            ],
        ],
        colWidths=[28 * mm, 90 * mm],
    )
    metadata.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "OJText"),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    return [
        Spacer(1, 32 * mm),
        Paragraph("PROGRAMMING PRACTICE / EXPERIMENT 02", kicker),
        Spacer(1, 8 * mm),
        Paragraph("在线评测系统", title),
        Paragraph("Atelier OJ", title),
        Spacer(1, 8 * mm),
        Table([["FASTAPI", "STREAMLIT", "LINUX RUNNER", "AI AUTHORING"]],
              colWidths=[32 * mm, 38 * mm, 42 * mm, 42 * mm],
              style=TableStyle([
                  ("BACKGROUND", (0, 0), (-1, -1), INK),
                  ("TEXTCOLOR", (0, 0), (-1, -1), ACID),
                  ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                  ("FONTSIZE", (0, 0), (-1, -1), 7),
                  ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                  ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
              ])),
        Spacer(1, 16 * mm),
        Paragraph(
            "一个具有真实异步评测、权限审计与可验证 AI 命题流程的课程级 Online Judge。",
            meta,
        ),
        Spacer(1, 22 * mm),
        metadata,
        Spacer(1, 18 * mm),
        Paragraph("2026 · PYTHON 3.12 · UBUNTU / WSL2", kicker),
        PageBreak(),
    ]


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    style_map = styles()
    document = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4,
        leftMargin=18 * mm, rightMargin=17 * mm,
        topMargin=18 * mm, bottomMargin=16 * mm,
        title="实验二：在线评测系统 — Atelier OJ",
        author="jasonpiggg",
        subject="程序设计训练（Python）实验报告",
    )
    story = cover_story(style_map) + parse_markdown(style_map)
    document.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    print(f"generated: {OUTPUT}")


if __name__ == "__main__":
    build()
