"""[service] XLSX 어댑터. openpyxl 로 시트를 표로 읽고 셀 값을 바꾸거나 채우며 HTML 표로 미리보기를 만든다."""

import re
import html
from typing import Any
from pathlib import Path
from openpyxl import load_workbook
from collections.abc import Mapping
from openpyxl.cell.cell import MergedCell

from docparse.template.template_schema import AnyLocator, FillValue, SheetCellLocator, PlaceholderLocator
from docparse.document_model import Cell, Document, Table, cell_id, table_id
from docparse.edit_plan import EditPlan

CELL = re.compile(r"^t(\d+)r(\d+)c(\d+)$")


def _as_value(original: Any, text: str) -> Any:
    """원래 숫자였던 칸에 숫자 꼴의 글이 오면 숫자로 둔다. 수식과 글은 그대로."""
    if isinstance(original, bool) or not isinstance(original, int | float):
        return text
    try:
        return int(text) if re.fullmatch(r"-?\d+", text.strip()) else float(text)
    except ValueError:
        return text


def _set_value(cell: Any, value: FillValue) -> None:
    cell.value = value
    if isinstance(value, str) and value.startswith("="):
        # 사용자가 준 값이 수식으로 저장되면 열 때 실행된다. 글로 둔다
        cell.data_type = "s"


def _replace_token(wb: Any, token: str, value: FillValue) -> int:
    """글 칸의 token 을 바꾼 칸 수. 칸 전체가 token 하나이고 값이 숫자면 숫자로 둔다. 수식 칸은 건드리지 않는다."""
    count = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type != "s" or not isinstance(cell.value, str) or token not in cell.value:
                    continue
                if cell.value == token and not isinstance(value, str):
                    _set_value(cell, value)
                else:
                    _set_value(cell, cell.value.replace(token, str(value)))
                count += 1
    return count


class XlsxAdapter:
    suffixes: tuple[str, ...] = (".xlsx",)

    def inspect(self, path: Path) -> Document:
        wb = load_workbook(str(path))
        try:
            return self._document(wb, path)
        finally:
            wb.close()

    def _document(self, wb: Any, path: Path) -> Document:
        tables: list[Table] = []
        for si, ws in enumerate(wb.worksheets):
            # 병합 범위의 왼쪽 위만 값이 있다. 나머지는 값이 없어 실리지 않는다.
            # 빈 병합 범위는 글을 적는 자리인 경우가 많아 왼쪽 위 칸을 빈 글로 싣는다
            spans = {
                str(rng.start_cell.coordinate): (rng.max_row - rng.min_row + 1, rng.max_col - rng.min_col + 1)
                for rng in ws.merged_cells.ranges
            }
            cells = tuple(
                Cell(
                    id=cell_id(si, c.row - 1, c.column - 1), row=c.row - 1, col=c.column - 1,
                    text="" if c.value is None else str(c.value), address=c.coordinate,
                    merged=c.coordinate in spans, row_span=spans.get(c.coordinate, (1, 1))[0],
                    col_span=spans.get(c.coordinate, (1, 1))[1],
                )
                for row in ws.iter_rows() for c in row if c.value is not None or c.coordinate in spans
            )
            tables.append(Table(
                id=table_id(si), index=si, rows=ws.max_row, cols=ws.max_column, cells=cells, name=ws.title
            ))
        return Document(path=str(path), format="xlsx", tables=tuple(tables))

    def replace(self, path: Path, plan: EditPlan, out_path: Path) -> Document:
        # ponytail: openpyxl 은 차트와 그림을 저장하지 않는다. 그런 양식이 나오면 LibreOffice 매크로로 바꾼다
        wb = load_workbook(str(path))
        try:
            for item in plan.replacements:
                m = CELL.match(item.target)
                if m is None:
                    raise KeyError(item.target)
                ws = wb.worksheets[int(m.group(1))]
                cell = ws.cell(row=int(m.group(2)) + 1, column=int(m.group(3)) + 1)
                cell.value = _as_value(cell.value, item.text)
            wb.save(str(out_path))
        finally:
            wb.close()
        return self.inspect(out_path)

    def fill(self, path: Path, assignments: Mapping[AnyLocator, FillValue], out_path: Path) -> Document:
        wb = load_workbook(str(path))
        try:
            for locator, value in assignments.items():
                self._fill_one(wb, locator, value)
            wb.save(str(out_path))
        finally:
            wb.close()
        return self.inspect(out_path)

    def _fill_one(self, wb: Any, locator: AnyLocator, value: FillValue) -> None:
        if isinstance(locator, PlaceholderLocator):
            if not _replace_token(wb, locator.token, value):
                raise KeyError(f"자리표시자가 없다: {locator.token}")
            return
        if not isinstance(locator, SheetCellLocator):
            raise KeyError(f"XLSX 에 쓸 수 없는 자리: {locator.kind}")
        if locator.sheet not in wb.sheetnames:
            raise KeyError(f"시트가 없다: {locator.sheet}")
        cell = wb[locator.sheet][locator.cell]
        if isinstance(cell, MergedCell):
            raise KeyError(f"병합 범위의 왼쪽 위 칸이 아니다: {locator.sheet}!{locator.cell}")
        _set_value(cell, value)

    def to_html(self, path: Path) -> str:
        doc = self.inspect(path)
        parts: list[str] = []
        for table in doc.tables:
            grid = {(c.row, c.col): c.text for c in table.cells}
            parts.append(f"<h2>{html.escape(table.name)}</h2><table>")
            for r in range(table.rows):
                row = "".join(f"<td>{html.escape(grid.get((r, c), ''))}</td>" for c in range(table.cols))
                parts.append(f"<tr>{row}</tr>")
            parts.append("</table>")
        return "".join(parts)
