"""[service] XLSX 어댑터. openpyxl 로 시트를 표로 읽고 셀 값을 바꾸며 HTML 표로 미리보기를 만든다."""

import re
import html
from typing import Any
from pathlib import Path
from openpyxl import load_workbook

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
            # 병합 범위의 왼쪽 위만 값이 있다. 나머지는 값이 없어 실리지 않는다
            heads = {str(rng.start_cell.coordinate) for rng in ws.merged_cells.ranges}
            cells = tuple(
                Cell(
                    id=cell_id(si, c.row - 1, c.column - 1), row=c.row - 1, col=c.column - 1, text=str(c.value),
                    address=c.coordinate, merged=c.coordinate in heads,
                )
                for row in ws.iter_rows() for c in row if c.value is not None
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
