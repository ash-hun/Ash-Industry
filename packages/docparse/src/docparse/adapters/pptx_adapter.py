"""[service] PPTX 어댑터. 글 도형과 표를 읽어 run 단위로 치환하거나 채우고, 노트와 차트 글은 읽기만 한다."""

import re
import html
from typing import Any
from pathlib import Path
from pptx import Presentation
from pptx.exc import PackageNotFoundError
from pptx.enum.shapes import MSO_SHAPE_TYPE
from collections.abc import Iterator, Mapping

from docparse.template.template_schema import (
    AnyLocator, FillValue, ShapeTextLocator, TableCellLocator, PlaceholderLocator,
)
from docparse.document_model import Cell, Document, Paragraph, Run, Table, cell_id, paragraph_id, table_id
from docparse.edit_plan import EditPlan

SHAPE_PARAGRAPH = re.compile(r"^s(\d+)sh(\d+)p(\d+)$")
CELL_PARAGRAPH = re.compile(r"^(t\d+r\d+c\d+)p(\d+)$")
CELL = re.compile(r"^t(\d+)r(\d+)c(\d+)$")


def shape_prefix(slide: int, shape_id: int) -> str:
    return f"s{slide}sh{shape_id}"


def _open(path: Path) -> Any:
    try:
        return Presentation(str(path))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise ValueError(f"PPTX 를 열 수 없다: {exc}") from exc


def _walk(shapes: Any) -> Iterator[Any]:
    """그룹 안까지 z 순서대로. shape_id 는 슬라이드 안에서 겹치지 않아 그룹 안 도형도 같은 규칙으로 가리킨다."""
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _walk(shape.shapes)
        else:
            yield shape


def _text_shapes(prs: Any) -> Iterator[tuple[int, Any]]:
    for si, slide in enumerate(prs.slides):
        for shape in _walk(slide.shapes):
            if shape.has_text_frame:
                yield si, shape


def _tables(prs: Any) -> list[tuple[int, Any]]:
    """슬라이드 순, 도형 순으로 센 표. 표 번호는 슬라이드를 가로질러 0부터다."""
    return [
        (si, shape.table)
        for si, slide in enumerate(prs.slides) for shape in _walk(slide.shapes)
        if getattr(shape, "has_table", False)
    ]


def _number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def _chart_lines(chart: Any) -> list[str]:
    """차트 제목, 항목, 계열마다 `이름: 값, 값`. 산점도처럼 항목이 없는 차트는 계열 값만."""
    lines: list[str] = []
    if chart.has_title and chart.chart_title.has_text_frame:
        title = chart.chart_title.text_frame.text.strip()
        if title:
            lines.append(title)
    for plot in chart.plots:
        try:
            categories = [str(c) for c in plot.categories]
        except (AttributeError, KeyError, ValueError):
            categories = []
        if categories:
            lines.append(f"항목: {', '.join(categories)}")
        for series in plot.series:
            values = ", ".join(_number(v) for v in series.values)
            lines.append(f"{series.name or '계열'}: {values}")
    return lines


def _readonly_paragraphs(slide: Any, si: int) -> list[Paragraph]:
    """차트(s<슬라이드>c<도형>p<줄>)와 노트(s<슬라이드>np<줄>). 쓰기 경로가 없어 읽기만 한다."""
    out: list[Paragraph] = []
    for shape in _walk(slide.shapes):
        if getattr(shape, "has_chart", False):
            prefix = f"s{si}c{shape.shape_id}"
            out.extend(
                Paragraph(id=paragraph_id(k, prefix), text=line, style="chart", editable=False)
                for k, line in enumerate(_chart_lines(shape.chart))
            )
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
        for k, para in enumerate(slide.notes_slide.notes_text_frame.paragraphs):
            text = _runs_text(para)
            if text.strip():
                out.append(Paragraph(id=paragraph_id(k, f"s{si}n"), text=text, style="notes", editable=False))
    return out


def _runs_text(para: Any) -> str:
    # 줄바꿈(a:br)은 run 이 아니다. 위치를 run 기준으로 재야 해서 para.text 를 쓰지 않는다
    return "".join(r.text for r in para.runs)


def _paragraph(para: Any, pid: str, style: str = "") -> Paragraph:
    runs = tuple(Run(id=f"{pid}.{i}", text=r.text) for i, r in enumerate(para.runs))
    return Paragraph(id=pid, text=_runs_text(para), runs=runs, style=style)


def _set_paragraph_text(para: Any, text: str) -> None:
    """첫 run 에 글을 넣고 나머지 run 은 지운다. 첫 run 의 글꼴, 굵기가 남는다."""
    runs = para.runs
    if not runs:
        para.add_run().text = text
        return
    runs[0].text = text
    for run in runs[1:]:
        run._r.getparent().remove(run._r)


def _set_frame_text(frame: Any, text: str) -> None:
    """첫 문단에 글을 넣고 나머지 문단은 지운다. 글 상자와 셀에는 문단이 하나는 남아야 한다."""
    paragraphs = frame.paragraphs
    _set_paragraph_text(paragraphs[0], text)
    for para in paragraphs[1:]:
        para._p.getparent().remove(para._p)


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
            run._r.getparent().remove(run._r)


def _replace_token(para: Any, token: str, text: str) -> int:
    """문단 안 token 을 모두 바꾼 횟수. 넣은 값 뒤부터 다시 찾아 값에 token 이 있어도 끝난다."""
    count = 0
    at = 0
    while (found := _runs_text(para).find(token, at)) >= 0:
        _replace_span(para, found, found + len(token), text)
        at = found + len(text)
        count += 1
    return count


def _unique_cells(table: Any) -> Iterator[tuple[int, int, Any]]:
    """병합에 덮인 칸(is_spanned)은 빼고 병합의 첫 칸만."""
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            if not cell.is_spanned:
                yield r, c, cell


class PptxAdapter:
    suffixes: tuple[str, ...] = (".pptx",)

    def inspect(self, path: Path) -> Document:
        return self._document(_open(path), path)

    def _document(self, prs: Any, path: Path) -> Document:
        # ponytail: 마스터와 레이아웃의 글은 읽지 않는다, 그런 양식이 나오면
        paragraphs: list[Paragraph] = []
        for si, slide in enumerate(prs.slides):
            for shape in _walk(slide.shapes):
                if not shape.has_text_frame:
                    continue
                prefix = shape_prefix(si, shape.shape_id)
                for k, para in enumerate(shape.text_frame.paragraphs):
                    paragraphs.append(_paragraph(para, paragraph_id(k, prefix), style=shape.name))
            paragraphs.extend(_readonly_paragraphs(slide, si))
        tables: list[Table] = []
        for ti, (si, table) in enumerate(_tables(prs)):
            cells: list[Cell] = []
            for r, c, cell in _unique_cells(table):
                cid = cell_id(ti, r, c)
                inner = tuple(_paragraph(p, f"{cid}p{k}") for k, p in enumerate(cell.text_frame.paragraphs))
                text = "\n".join(p.text for p in inner)
                cells.append(Cell(
                    id=cid, row=r, col=c, text=text, paragraphs=inner, merged=cell.is_merge_origin,
                    row_span=cell.span_height if cell.is_merge_origin else 1,
                    col_span=cell.span_width if cell.is_merge_origin else 1,
                ))
            tables.append(Table(
                id=table_id(ti), index=ti, rows=len(table.rows), cols=len(table.columns), cells=tuple(cells),
                name=f"슬라이드 {si + 1}",
            ))
        meta = {"slides": str(len(prs.slides))}
        return Document(
            path=str(path), format="pptx", paragraphs=tuple(paragraphs), tables=tuple(tables), meta=meta,
        )

    def replace(self, path: Path, plan: EditPlan, out_path: Path) -> Document:
        prs = _open(path)
        for item in plan.replacements:
            self._apply_one(prs, item.target, item.text)
        prs.save(str(out_path))
        return self.inspect(out_path)

    def _apply_one(self, prs: Any, target: str, text: str) -> None:
        if m := SHAPE_PARAGRAPH.match(target):
            frame = self._shape(prs, int(m.group(1)), int(m.group(2))).text_frame
            _set_paragraph_text(self._at(frame.paragraphs, int(m.group(3)), target), text)
            return
        if m := CELL_PARAGRAPH.match(target):
            cell = self._cell(prs, m.group(1))
            _set_paragraph_text(self._at(cell.text_frame.paragraphs, int(m.group(2)), target), text)
            return
        if CELL.match(target):
            _set_frame_text(self._cell(prs, target).text_frame, text)
            return
        raise KeyError(target)

    def _at(self, items: Any, index: int, target: str) -> Any:
        if index >= len(items):
            raise KeyError(target)
        return items[index]

    def _shape(self, prs: Any, slide: int, shape_id: int) -> Any:
        found = next((s for si, s in _text_shapes(prs) if si == slide and s.shape_id == shape_id), None)
        if found is None:
            raise KeyError(f"글 도형이 없다: {shape_prefix(slide, shape_id)}")
        return found

    def _cell(self, prs: Any, cid: str) -> Any:
        m = CELL.match(cid)
        tables = _tables(prs)
        if m is None or int(m.group(1)) >= len(tables):
            raise KeyError(cid)
        table = tables[int(m.group(1))][1]
        row, col = int(m.group(2)), int(m.group(3))
        if row >= len(table.rows) or col >= len(table.columns):
            raise KeyError(cid)
        return table.cell(row, col)

    def fill(self, path: Path, assignments: Mapping[AnyLocator, FillValue], out_path: Path) -> Document:
        prs = _open(path)
        for locator, value in assignments.items():
            self._fill_one(prs, locator, str(value))
        prs.save(str(out_path))
        return self.inspect(out_path)

    def _fill_one(self, prs: Any, locator: AnyLocator, text: str) -> None:
        if isinstance(locator, PlaceholderLocator):
            paragraphs = [p for _, s in _text_shapes(prs) for p in s.text_frame.paragraphs]
            paragraphs += [
                p for _, table in _tables(prs) for _, _, cell in _unique_cells(table)
                for p in cell.text_frame.paragraphs
            ]
            if not sum(_replace_token(p, locator.token, text) for p in paragraphs):
                raise KeyError(f"자리표시자가 없다: {locator.token}")
            return
        if isinstance(locator, ShapeTextLocator):
            _set_frame_text(self._shape(prs, locator.slide, locator.shape).text_frame, text)
            return
        if isinstance(locator, TableCellLocator):
            _set_frame_text(self._cell(prs, cell_id(locator.table, locator.row, locator.col)).text_frame, text)
            return
        raise KeyError(f"PPTX 에 쓸 수 없는 자리: {locator.kind}")

    def to_html(self, path: Path) -> str:
        doc = self.inspect(path)
        slides = int(doc.meta.get("slides", "0"))
        parts: list[str] = []
        for si in range(slides):
            parts.append(f"<section><h2>슬라이드 {si + 1}</h2>")
            body = [p for p in doc.paragraphs if p.id.startswith(f"s{si}sh") and p.text.strip()]
            parts.extend(f"<p>{html.escape(p.text)}</p>" for p in body)
            charts = [p for p in doc.paragraphs if p.id.startswith(f"s{si}c")]
            parts.extend(f"<p class=\"chart\">{html.escape(p.text)}</p>" for p in charts)
            for table in (t for t in doc.tables if t.name == f"슬라이드 {si + 1}"):
                grid = {(c.row, c.col): c.text for c in table.cells}
                parts.append("<table>")
                for r in range(table.rows):
                    row = "".join(f"<td>{html.escape(grid.get((r, c), ''))}</td>" for c in range(table.cols))
                    parts.append(f"<tr>{row}</tr>")
                parts.append("</table>")
            notes = [p for p in doc.paragraphs if p.id.startswith(f"s{si}np")]
            if notes:
                parts.append("<h3>노트</h3>")
                parts.extend(f"<p class=\"notes\">{html.escape(p.text)}</p>" for p in notes)
            parts.append("</section>")
        return "".join(parts)
