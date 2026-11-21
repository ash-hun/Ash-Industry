"""[service] DOCX 어댑터. python-docx 로 읽고 run 단위로 치환하며 mammoth 로 HTML 미리보기를 만든다."""

import re
import mammoth
from typing import Any
from pathlib import Path
from docx import Document as load_docx

from docparse.document_model import Cell, Document, Paragraph, Run, Table, cell_id, paragraph_id, table_id
from docparse.edit_plan import EditPlan

CELL_PARAGRAPH = re.compile(r"^(t\d+r\d+c\d+)p(\d+)$")
CELL = re.compile(r"^t(\d+)r(\d+)c(\d+)$")
BODY_PARAGRAPH = re.compile(r"^p(\d+)$")


def _paragraph(para: Any, pid: str) -> Paragraph:
    runs = tuple(Run(id=f"{pid}.{i}", text=r.text) for i, r in enumerate(para.runs))
    # 기본 스타일(Normal)은 정보가 없어 비운다
    style = para.style.name if para.style is not None and para.style.name and para.style.name != "Normal" else ""
    return Paragraph(id=pid, text=para.text, runs=runs, style=style)


def _set_paragraph_text(para: Any, text: str) -> None:
    """첫 run 에 글을 넣고 나머지 run 은 지운다. 첫 run 의 글꼴, 굵기가 남는다."""
    runs = para.runs
    if not runs:
        para.add_run(text)
        return
    runs[0].text = text
    for run in runs[1:]:
        run._element.getparent().remove(run._element)


def _set_cell_text(cell: Any, text: str) -> None:
    """첫 문단에 글을 넣고 나머지 문단은 지운다. 셀에는 문단이 하나는 남아야 한다."""
    paragraphs = cell.paragraphs
    _set_paragraph_text(paragraphs[0], text)
    for para in paragraphs[1:]:
        para._element.getparent().remove(para._element)


class DocxAdapter:
    suffixes: tuple[str, ...] = (".docx",)

    def inspect(self, path: Path) -> Document:
        doc = load_docx(str(path))
        return self._document(doc, path)

    def _document(self, doc: Any, path: Path) -> Document:
        paragraphs = tuple(_paragraph(p, paragraph_id(i)) for i, p in enumerate(doc.paragraphs))
        tables: list[Table] = []
        for ti, table in enumerate(doc.tables):
            cells: list[Cell] = []
            # 병합된 칸은 같은 요소가 되풀이된다. 처음 것만 싣는다.
            # 목록으로 쥐고 있어야 lxml 프록시가 살아 같은 요소로 비교된다
            # ponytail: 중첩 표는 읽지 않는다, 공고 양식에서 나오면
            seen: list[Any] = []
            rows = table.rows
            for r, row in enumerate(rows):
                for c, cell in enumerate(row.cells):
                    if any(cell._tc is tc for tc in seen):
                        continue
                    seen.append(cell._tc)
                    cid = cell_id(ti, r, c)
                    inner = tuple(_paragraph(p, f"{cid}p{k}") for k, p in enumerate(cell.paragraphs))
                    merged = bool(cell._tc.xpath("./w:tcPr/w:gridSpan") or cell._tc.xpath("./w:tcPr/w:vMerge"))
                    cells.append(Cell(id=cid, row=r, col=c, text=cell.text, paragraphs=inner, merged=merged))
            tables.append(
                Table(id=table_id(ti), index=ti, rows=len(rows), cols=len(table.columns), cells=tuple(cells))
            )
        return Document(path=str(path), format="docx", paragraphs=paragraphs, tables=tuple(tables))

    def replace(self, path: Path, plan: EditPlan, out_path: Path) -> Document:
        doc = load_docx(str(path))
        for item in plan.replacements:
            self._apply_one(doc, item.target, item.text)
        doc.save(str(out_path))
        return self._document(load_docx(str(out_path)), out_path)

    def _apply_one(self, doc: Any, target: str, text: str) -> None:
        if m := BODY_PARAGRAPH.match(target):
            _set_paragraph_text(doc.paragraphs[int(m.group(1))], text)
            return
        if m := CELL_PARAGRAPH.match(target):
            cell = self._cell(doc, m.group(1))
            _set_paragraph_text(cell.paragraphs[int(m.group(2))], text)
            return
        if CELL.match(target):
            _set_cell_text(self._cell(doc, target), text)
            return
        raise KeyError(target)

    def _cell(self, doc: Any, cid: str) -> Any:
        m = CELL.match(cid)
        if m is None:
            raise KeyError(cid)
        table = doc.tables[int(m.group(1))]
        return table.rows[int(m.group(2))].cells[int(m.group(3))]

    def to_html(self, path: Path) -> str:
        with open(path, "rb") as f:
            result = mammoth.convert_to_html(f)
        return str(result.value)
