"""[service] 내용 명세로 새 DOCX, XLSX, PPTX 를 쓴다. 서식은 각 라이브러리의 기본 템플릿을 따른다."""

from pathlib import Path
from typing import Literal
from pptx.util import Inches
from openpyxl import Workbook
from pptx import Presentation
from docx import Document as new_docx
from pydantic import Field, BaseModel

CREATE_SUFFIXES: tuple[str, ...] = (".docx", ".xlsx", ".pptx")
# python-pptx 기본 템플릿의 레이아웃 순서
TITLE_LAYOUT, CONTENT_LAYOUT, TITLE_ONLY_LAYOUT = 0, 1, 5

CellValue = str | int | float | bool | None


class Block(BaseModel):
    """DOCX 본문 한 덩어리. heading, paragraph 는 text, bullets 는 items, table 은 rows(첫 줄이 머리글)."""

    type: Literal["heading", "paragraph", "bullets", "table"]
    text: str = ""
    level: int = Field(default=1, ge=1, le=3)
    items: list[str] = Field(default_factory=list, max_length=200)
    rows: list[list[str]] = Field(default_factory=list, max_length=500)


class SlideSpec(BaseModel):
    """PPTX 슬라이드 하나. bullets 나 table 이 없고 subtitle 만 있으면 표지 레이아웃이다."""

    title: str = ""
    subtitle: str = ""
    bullets: list[str] = Field(default_factory=list, max_length=30)
    table: list[list[str]] = Field(default_factory=list, max_length=50)
    notes: str = ""


class SheetSpec(BaseModel):
    name: str = Field(min_length=1, max_length=31)
    rows: list[list[CellValue]] = Field(default_factory=list, max_length=10000)


class DocumentSpec(BaseModel):
    """만들 문서의 내용. 확장자에 맞는 칸만 쓴다: DOCX 는 blocks, PPTX 는 slides, XLSX 는 sheets."""

    title: str = ""
    blocks: list[Block] = Field(default_factory=list, max_length=1000)
    slides: list[SlideSpec] = Field(default_factory=list, max_length=100)
    sheets: list[SheetSpec] = Field(default_factory=list, max_length=20)


def spec_issues(spec: DocumentSpec, suffix: str) -> list[str]:
    """만들기 전에 내용이 확장자와 맞는지 본다. 빈 목록이면 만들 수 있다."""
    issues: list[str] = []
    if suffix not in CREATE_SUFFIXES:
        return [f"새로 만들 수 있는 형식은 {', '.join(CREATE_SUFFIXES)} 이다: {suffix or '(확장자 없음)'}"]
    used = {"blocks": bool(spec.blocks), "slides": bool(spec.slides), "sheets": bool(spec.sheets)}
    wanted = {".docx": "blocks", ".pptx": "slides", ".xlsx": "sheets"}[suffix]
    issues += [
        f"{suffix} 에는 {name} 를 쓰지 않는다. {wanted} 를 쓴다" for name, on in used.items() if on and name != wanted
    ]
    if suffix == ".docx" and not (spec.blocks or spec.title):
        issues.append("DOCX 에 넣을 title 이나 blocks 가 없다")
    if suffix == ".pptx" and not spec.slides:
        issues.append("PPTX 에 넣을 slides 가 없다")
    if suffix == ".xlsx" and not spec.sheets:
        issues.append("XLSX 에 넣을 sheets 가 없다")
    for i, block in enumerate(spec.blocks):
        if block.type in ("heading", "paragraph") and not block.text:
            issues.append(f"blocks[{i}]: {block.type} 에 text 가 없다")
        if block.type == "bullets" and not block.items:
            issues.append(f"blocks[{i}]: bullets 에 items 가 없다")
        if block.type == "table" and not block.rows:
            issues.append(f"blocks[{i}]: table 에 rows 가 없다")
    for i, slide in enumerate(spec.slides):
        if slide.bullets and slide.table:
            issues.append(f"slides[{i}]: bullets 와 table 은 한 슬라이드에 함께 넣지 않는다. 슬라이드를 나눈다")
        if not (slide.title or slide.subtitle or slide.bullets or slide.table):
            issues.append(f"slides[{i}]: 빈 슬라이드다")
    names = [s.name for s in spec.sheets]
    if len(set(names)) != len(names):
        issues.append("시트 이름이 겹친다")
    return issues


def _width(rows: list[list[str]]) -> int:
    return max((len(r) for r in rows), default=0)


def _write_docx(spec: DocumentSpec, out_path: Path) -> None:
    doc = new_docx()
    if spec.title:
        doc.add_heading(spec.title, 0)
    for block in spec.blocks:
        if block.type == "heading":
            doc.add_heading(block.text, block.level)
        elif block.type == "paragraph":
            doc.add_paragraph(block.text)
        elif block.type == "bullets":
            for item in block.items:
                doc.add_paragraph(item, style="List Bullet")
        else:
            table = doc.add_table(rows=len(block.rows), cols=_width(block.rows), style="Table Grid")
            for r, row in enumerate(block.rows):
                for c, text in enumerate(row):
                    table.cell(r, c).text = text
    doc.save(str(out_path))


def _write_pptx(spec: DocumentSpec, out_path: Path) -> None:
    # ponytail: 기본 템플릿의 4:3 그대로다. 16:9 로 바꾸면 레이아웃 자리표시자 위치를 다시 잡아야 한다
    prs = Presentation()
    for slide_spec in spec.slides:
        cover = not (slide_spec.bullets or slide_spec.table)
        layout = TITLE_LAYOUT if cover else CONTENT_LAYOUT if slide_spec.bullets else TITLE_ONLY_LAYOUT
        slide = prs.slides.add_slide(prs.slide_layouts[layout])
        slide.shapes.title.text = slide_spec.title
        if cover:
            slide.placeholders[1].text = slide_spec.subtitle
        elif slide_spec.bullets:
            body = slide.placeholders[1].text_frame
            body.text = slide_spec.bullets[0]
            for item in slide_spec.bullets[1:]:
                body.add_paragraph().text = item
        else:
            rows, cols = len(slide_spec.table), _width(slide_spec.table)
            top = Inches(1.5)
            frame = slide.shapes.add_table(
                rows, cols, Inches(0.5), top, prs.slide_width - Inches(1), Inches(0.4) * rows,
            )
            for r, row in enumerate(slide_spec.table):
                for c, text in enumerate(row):
                    frame.table.cell(r, c).text = text
        if slide_spec.notes:
            slide.notes_slide.notes_text_frame.text = slide_spec.notes
    prs.save(str(out_path))


def _write_xlsx(spec: DocumentSpec, out_path: Path) -> None:
    wb = Workbook()
    first = wb.active
    for i, sheet_spec in enumerate(spec.sheets):
        ws = first if i == 0 and first is not None else wb.create_sheet()
        ws.title = sheet_spec.name
        for row in sheet_spec.rows:
            ws.append(row)
    wb.save(str(out_path))


def create(spec: DocumentSpec, out_path: Path) -> Path:
    """out_path 확장자에 맞춰 새 파일을 쓴다. 내용이 맞지 않으면 ValueError. 이미 있는 파일은 덮어쓰지 않는다."""
    suffix = out_path.suffix.lower()
    issues = spec_issues(spec, suffix)
    if issues:
        raise ValueError("; ".join(issues))
    if out_path.exists():
        raise FileExistsError(f"이미 있는 파일이다: {out_path.name}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = {".docx": _write_docx, ".pptx": _write_pptx, ".xlsx": _write_xlsx}[suffix]
    # 숨김 임시 파일에 다 쓴 뒤 이름을 바꾼다. 중간에 멈춰도 반쯤 쓴 결과가 목록에 보이지 않는다
    tmp = out_path.with_name(f".{out_path.stem}.creating{suffix}")
    try:
        writer(spec, tmp)
        tmp.rename(out_path)
    finally:
        tmp.unlink(missing_ok=True)
    return out_path
