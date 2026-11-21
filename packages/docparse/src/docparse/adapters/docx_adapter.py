"""[service] DOCX 어댑터. python-docx 로 읽고 run 단위로 치환하거나 양식을 채우며 mammoth 로 HTML 미리보기를 만든다."""

import re
import mammoth
from typing import Any
from pathlib import Path
from collections.abc import Mapping
from docx import Document as load_docx

from docparse.template.template_schema import (
    AnyLocator, FillValue, TableCellLocator, AnchorTextLocator, PlaceholderLocator,
)
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


def _runs_text(para: Any) -> str:
    # 하이퍼링크 안 run 은 para.runs 에 없다. 위치를 run 기준으로 재야 해서 para.text 를 쓰지 않는다
    return "".join(r.text for r in para.runs)


def _replace_span(para: Any, start: int, end: int, text: str) -> None:
    """run 을 이은 글의 [start, end) 를 text 로. 시작 run 의 서식을 쓰고, 걸친 run 은 걸친 글자만 지운다."""
    pos = 0
    first = True
    for run in list(para.runs):
        body = run.text
        run_start, run_end = pos, pos + len(body)
        pos = run_end
        if run_end <= start or run_start >= end:
            continue
        head = body[: max(start - run_start, 0)]
        tail = body[end - run_start :] if end < run_end else ""
        if first:
            run.text = head + text + tail
            first = False
        elif tail:
            run.text = tail
        else:
            run._element.getparent().remove(run._element)


def _replace_token(para: Any, token: str, text: str) -> int:
    """문단 안 token 을 모두 바꾼 횟수. 넣은 값 뒤부터 다시 찾아 값에 token 이 있어도 끝난다."""
    count = 0
    at = 0
    while (found := _runs_text(para).find(token, at)) >= 0:
        _replace_span(para, found, found + len(token), text)
        at = found + len(text)
        count += 1
    return count


def _fill_after_anchor(paragraphs: list[Any], anchor: str, text: str) -> bool:
    """anchor 뒤에 글이 있으면 그 글을, 없으면 anchor 가 없는 다음 문단을 바꾼다. anchor 가 없으면 False."""
    for i, para in enumerate(paragraphs):
        joined = _runs_text(para)
        at = joined.find(anchor)
        if at < 0:
            continue
        rest = joined[at + len(anchor) :]
        if rest.strip():
            # 기준 글과 값 사이 띄어쓰기는 원래대로 둔다
            start = at + len(anchor) + len(rest) - len(rest.lstrip())
            _replace_span(para, start, len(joined), text)
            return True
        following = next((p for p in paragraphs[i + 1 :] if anchor not in p.text), None)
        if following is None:
            raise KeyError(f"기준 글 뒤에 채울 문단이 없다: {anchor!r}")
        _set_paragraph_text(following, text)
        return True
    return False


def _unique_cells(doc: Any) -> list[Any]:
    """병합된 칸은 row.cells 에 되풀이된다. 같은 요소는 한 번만."""
    seen: list[Any] = []
    cells: list[Any] = []
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if not any(cell._tc is tc for tc in seen):
                    seen.append(cell._tc)
                    cells.append(cell)
    return cells


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

    def fill(self, path: Path, assignments: Mapping[AnyLocator, FillValue], out_path: Path) -> Document:
        # ponytail: 머리글, 바닥글, 중첩 표, 하이퍼링크 안은 채우지 않는다, 그런 양식이 나오면
        doc = load_docx(str(path))
        for locator, value in assignments.items():
            self._fill_one(doc, locator, str(value))
        doc.save(str(out_path))
        return self._document(load_docx(str(out_path)), out_path)

    def _fill_one(self, doc: Any, locator: AnyLocator, text: str) -> None:
        if isinstance(locator, PlaceholderLocator):
            paragraphs = list(doc.paragraphs) + [p for c in _unique_cells(doc) for p in c.paragraphs]
            if not sum(_replace_token(p, locator.token, text) for p in paragraphs):
                raise KeyError(f"자리표시자가 없다: {locator.token}")
            return
        if isinstance(locator, TableCellLocator):
            try:
                cell = doc.tables[locator.table].rows[locator.row].cells[locator.col]
            except IndexError as exc:
                raise KeyError(cell_id(locator.table, locator.row, locator.col)) from exc
            _set_cell_text(cell, text)
            return
        if isinstance(locator, AnchorTextLocator):
            # 본문 문단을 먼저 보고, 없으면 표 칸마다 그 칸의 문단 안에서 찾는다
            scopes = [list(doc.paragraphs)] + [list(c.paragraphs) for c in _unique_cells(doc)]
            if not any(_fill_after_anchor(scope, locator.after, text) for scope in scopes):
                raise KeyError(f"기준 글이 없다: {locator.after!r}")
            return
        raise KeyError(f"DOCX 에 쓸 수 없는 자리: {locator.kind}")

    def to_html(self, path: Path) -> str:
        with open(path, "rb") as f:
            result = mammoth.convert_to_html(f)
        return str(result.value)
