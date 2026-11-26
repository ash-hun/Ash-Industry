"""[service] HWPX 어댑터. python-hwpx 로 HWPX 와 HWP 를 읽고 run 단위로 치환하거나 양식을 채워 HWPX 로 저장한다."""

import re
import html
import warnings
from typing import Any
from pathlib import Path
from collections.abc import Iterator, Mapping
from hwpx.opc.package import HwpxPackageError
from hwpx import HwpxError, HwpxDocument, Hwp5ConversionWarning

from docparse.template.template_schema import (
    AnyLocator, FillValue, CheckboxLocator, TableCellLocator, InlineSlotLocator, AnchorTextLocator, PlaceholderLocator,
)
from docparse.document_model import Cell, Document, Paragraph, Run, Table, cell_id, paragraph_id, table_id
from docparse.template.slot_text import BOX_EMPTY, BOX_CHECKED, slot_span, box_positions
from docparse.edit_plan import EditPlan

CELL_PARAGRAPH = re.compile(r"^(t\d+r\d+c\d+)p(\d+)$")
CELL = re.compile(r"^t(\d+)r(\d+)c(\d+)$")
BODY_PARAGRAPH = re.compile(r"^p(\d+)$")
# 바탕글은 스타일 정보가 없어 DOCX 의 Normal 처럼 비운다
DEFAULT_STYLE_ID = "0"


def _open(path: Path) -> Any:
    """HWP 는 python-hwpx 가 HWPX 모델로 바꿔 연다. 옮기지 못한 내용은 경고 대신 meta 에 적는다."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Hwp5ConversionWarning)
            return HwpxDocument.open(path)
    except (HwpxError, HwpxPackageError) as exc:
        raise ValueError(f"HWP/HWPX 를 열 수 없다: {exc}") from exc


def _save(doc: Any, out_path: Path) -> None:
    # .hwp 경로로 저장하면 python-hwpx 가 HWP 5.0 으로 쓴다. 쓰기는 HWPX 하나로 묶는다
    if out_path.suffix.lower() != ".hwpx":
        raise ValueError(f"HWPX 로만 저장한다: {out_path.name}")
    # 손대지 않은 파트는 바이트 그대로 둔다. HWP 에서 바꿔 연 문서는 원본 파트가 없어 다시 묶는다
    fallback = "rebuild" if doc.conversion_report is not None else "error"
    try:
        doc.save_to_path(out_path, mode="patch", fallback=fallback)
    except HwpxError as exc:
        raise ValueError(f"HWPX 저장 실패: {exc}") from exc


def _text_only(run: Any) -> bool:
    """표, 구역 설정, 컨트롤이 든 run 은 지우면 안 된다."""
    return bool(run.content_kinds() <= {"text"})


def _runs_text(para: Any) -> str:
    # 위치를 run 기준으로 재야 해서 탭을 따로 세는 para.text 를 쓰지 않는다
    return "".join(r.text for r in para.runs)


def _style_name(doc: Any, style_id: str | None) -> str:
    if not style_id or style_id == DEFAULT_STYLE_ID:
        return ""
    style = doc.styles.get(style_id)
    return str(style.name) if style is not None and style.name else ""


def _paragraph(doc: Any, para: Any, pid: str) -> Paragraph:
    runs = tuple(Run(id=f"{pid}.{i}", text=r.text) for i, r in enumerate(para.runs))
    return Paragraph(id=pid, text=para.text, runs=runs, style=_style_name(doc, para.style_id_ref))


def _set_paragraph_text(para: Any, text: str) -> None:
    """글이 있는 첫 run 에 넣고 나머지 run 의 글은 지운다. 그 run 의 글자 모양(charPrIDRef)이 남는다."""
    runs = para.runs
    keep = next((r for r in runs if r.text), runs[0] if runs else None)
    if keep is None:
        para.text = text
        return
    keep.text = text
    for run in runs:
        if run.element is keep.element or not run.text:
            continue
        if _text_only(run):
            run.remove()
        else:
            run.text = ""


def _set_cell_text(cell: Any, text: str) -> None:
    """첫 문단에 넣고 나머지 문단은 지운다. 안에 표가 든 문단은 남긴다."""
    paragraphs = cell.paragraphs
    _set_paragraph_text(paragraphs[0], text)
    for para in paragraphs[1:]:
        if not para.tables:
            para.remove()


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
        elif tail or not _text_only(run):
            run.text = tail
        else:
            run.remove()


def _replace_token(para: Any, token: str, text: str) -> int:
    """문단 안 token 을 모두 바꾼 횟수. 넣은 값 뒤부터 다시 찾아 값에 token 이 있어도 끝난다."""
    count = 0
    at = 0
    while (found := _runs_text(para).find(token, at)) >= 0:
        _replace_span(para, found, found + len(token), text)
        at = found + len(text)
        count += 1
    return count


def _fill_inline(para: Any, locator: InlineSlotLocator | CheckboxLocator, text: str) -> None:
    """빈 괄호는 안쪽만, 체크 칸은 칸 기호 한 글자씩 바꾼다. 둘레 글과 run 서식은 그대로다."""
    joined = _runs_text(para)
    if isinstance(locator, InlineSlotLocator):
        span = slot_span(joined, locator.label)
        if span is None:
            raise KeyError(f"빈 괄호가 없다: {locator.paragraph} {locator.label!r}")
        _replace_span(para, span[0], span[1], text)
        return
    positions = box_positions(joined, locator.options)
    if positions is None:
        raise KeyError(f"선택지 칸이 없다: {locator.paragraph}")
    for option, at in positions.items():
        _replace_span(para, at, at + 1, BOX_CHECKED if option == text else BOX_EMPTY)


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


def _tables(doc: Any) -> list[Any]:
    # ponytail: 본문 문단에 바로 든 표만 센다(셀 안 표, 글상자 안 표는 빼고), 공고 양식에서 나오면
    return [t for p in doc.paragraphs for t in p.tables]


def _table_anchors(doc: Any) -> list[int]:
    """_tables 와 같은 순서로, 표마다 그 앞에 오는 본문 문단 수. 표는 그것을 품은 문단 바로 뒤에 둔다."""
    return [i + 1 for i, p in enumerate(doc.paragraphs) for _ in p.tables]


def _anchors(table: Any) -> Iterator[Any]:
    """병합된 칸은 격자 여러 자리에 같은 셀로 나온다. 왼쪽 위 자리만."""
    return (entry for entry in table.iter_grid() if entry.is_anchor)


def _unique_cells(doc: Any) -> list[Any]:
    return [entry.cell for table in _tables(doc) for entry in _anchors(table)]


def _conversion_meta(doc: Any) -> dict[str, str]:
    report = doc.conversion_report
    if report is None:
        return {}
    lost = {**report.unconverted, **report.dropped}
    if not lost:
        return {"source_format": "hwp"}
    return {"source_format": "hwp", "unconverted": ", ".join(f"{k} x{v}" for k, v in sorted(lost.items()))}


def _table_html(table: Any) -> str:
    rows: dict[int, list[str]] = {}
    for entry in _anchors(table):
        span = ""
        if entry.row_span > 1:
            span += f' rowspan="{entry.row_span}"'
        if entry.col_span > 1:
            span += f' colspan="{entry.col_span}"'
        body = "<br>".join(html.escape(p.text) for p in entry.cell.paragraphs)
        rows.setdefault(entry.row, []).append(f"<td{span}>{body}</td>")
    return "<table>" + "".join(f"<tr>{''.join(rows.get(r, []))}</tr>" for r in range(table.row_count)) + "</table>"


class HwpxAdapter:
    """HWP 도 읽지만 쓰기는 늘 HWPX 다. 결과 경로의 확장자는 부르는 쪽이 .hwpx 로 정한다."""

    suffixes: tuple[str, ...] = (".hwpx", ".hwp")

    def inspect(self, path: Path) -> Document:
        with _open(path) as doc:
            return self._document(doc, path)

    def _document(self, doc: Any, path: Path) -> Document:
        paragraphs = tuple(_paragraph(doc, p, paragraph_id(i)) for i, p in enumerate(doc.paragraphs))
        tables: list[Table] = []
        anchors = _table_anchors(doc)
        for ti, table in enumerate(_tables(doc)):
            cells: list[Cell] = []
            for entry in _anchors(table):
                cid = cell_id(ti, entry.row, entry.column)
                inner = tuple(_paragraph(doc, p, f"{cid}p{k}") for k, p in enumerate(entry.cell.paragraphs))
                cells.append(Cell(
                    id=cid, row=entry.row, col=entry.column, text=entry.cell.text, paragraphs=inner,
                    merged=entry.span != (1, 1), row_span=entry.row_span, col_span=entry.col_span,
                ))
            tables.append(Table(
                id=table_id(ti), index=ti, rows=table.row_count, cols=table.column_count, cells=tuple(cells),
                anchor=anchors[ti],
            ))
        fmt = "hwp" if path.suffix.lower() == ".hwp" else "hwpx"
        return Document(
            path=str(path), format=fmt, paragraphs=paragraphs, tables=tuple(tables), meta=_conversion_meta(doc),
        )

    def replace(self, path: Path, plan: EditPlan, out_path: Path) -> Document:
        with _open(path) as doc:
            for item in plan.replacements:
                self._apply_one(doc, item.target, item.text)
            _save(doc, out_path)
        return self.inspect(out_path)

    def _apply_one(self, doc: Any, target: str, text: str) -> None:
        if m := BODY_PARAGRAPH.match(target):
            _set_paragraph_text(self._at(doc.paragraphs, int(m.group(1)), target), text)
            return
        if m := CELL_PARAGRAPH.match(target):
            cell = self._cell(doc, m.group(1))
            _set_paragraph_text(self._at(cell.paragraphs, int(m.group(2)), target), text)
            return
        if CELL.match(target):
            _set_cell_text(self._cell(doc, target), text)
            return
        raise KeyError(target)

    def _at(self, items: list[Any], index: int, target: str) -> Any:
        if index >= len(items):
            raise KeyError(target)
        return items[index]

    def _cell(self, doc: Any, cid: str) -> Any:
        m = CELL.match(cid)
        if m is None:
            raise KeyError(cid)
        table = self._at(_tables(doc), int(m.group(1)), cid)
        try:
            return table.cell(int(m.group(2)), int(m.group(3)))
        except IndexError as exc:
            raise KeyError(cid) from exc

    def fill(self, path: Path, assignments: Mapping[AnyLocator, FillValue], out_path: Path) -> Document:
        # ponytail: 머리글, 바닥글, 각주, 글상자, 셀 안 표는 채우지 않는다, 그런 양식이 나오면
        with _open(path) as doc:
            for locator, value in assignments.items():
                self._fill_one(doc, locator, str(value))
            _save(doc, out_path)
        return self.inspect(out_path)

    def _fill_one(self, doc: Any, locator: AnyLocator, text: str) -> None:
        if isinstance(locator, PlaceholderLocator):
            paragraphs = list(doc.paragraphs) + [p for c in _unique_cells(doc) for p in c.paragraphs]
            if not sum(_replace_token(p, locator.token, text) for p in paragraphs):
                raise KeyError(f"자리표시자가 없다: {locator.token}")
            return
        if isinstance(locator, TableCellLocator):
            _set_cell_text(self._cell(doc, cell_id(locator.table, locator.row, locator.col)), text)
            return
        if isinstance(locator, AnchorTextLocator):
            # 본문 문단을 먼저 보고, 없으면 표 칸마다 그 칸의 문단 안에서 찾는다
            scopes = [list(doc.paragraphs)] + [list(c.paragraphs) for c in _unique_cells(doc)]
            if not any(_fill_after_anchor(scope, locator.after, text) for scope in scopes):
                raise KeyError(f"기준 글이 없다: {locator.after!r}")
            return
        if isinstance(locator, InlineSlotLocator | CheckboxLocator):
            _fill_inline(self._paragraph(doc, locator.paragraph), locator, text)
            return
        raise KeyError(f"HWPX 에 쓸 수 없는 자리: {locator.kind}")

    def _paragraph(self, doc: Any, pid: str) -> Any:
        if m := BODY_PARAGRAPH.match(pid):
            return self._at(doc.paragraphs, int(m.group(1)), pid)
        if m := CELL_PARAGRAPH.match(pid):
            return self._at(self._cell(doc, m.group(1)).paragraphs, int(m.group(2)), pid)
        raise KeyError(f"문단이 없다: {pid}")

    def to_html(self, path: Path) -> str:
        """문단과 표를 문서 순서대로. 병합은 rowspan, colspan 으로 옮기고 글은 모두 이스케이프한다."""
        parts: list[str] = []
        with _open(path) as doc:
            for para in doc.paragraphs:
                parts.append(f"<p>{html.escape(para.text)}</p>")
                for table in para.tables:
                    parts.append(_table_html(table))
        return "".join(parts)

