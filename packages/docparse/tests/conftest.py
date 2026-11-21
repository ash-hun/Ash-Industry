"""docparse 테스트가 쓰는 작은 실제 파일. 샘플 양식 대신 코드로 만든다."""

import pytest
from pathlib import Path
from openpyxl import Workbook
from docx import Document as new_docx


@pytest.fixture
def docx_path(tmp_path: Path) -> Path:
    doc = new_docx()
    doc.add_paragraph("출장 신청서", style="Title")
    para = doc.add_paragraph()
    para.add_run("신청자: ").bold = True
    para.add_run("홍길동")
    doc.add_paragraph("")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "출장 기간"
    table.cell(0, 1).text = "{{출장기간}}"
    table.cell(1, 0).text = "출장 목적"
    cell = table.cell(1, 1)
    cell.text = "첫 줄"
    cell.add_paragraph("둘째 줄")
    path = tmp_path / "출장신청서.docx"
    doc.save(str(path))
    return path


@pytest.fixture
def xlsx_path(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "경비"
    ws["A1"] = "항목"
    ws["B1"] = "금액"
    ws["A2"] = "숙박"
    ws["B2"] = 120000
    ws["A3"] = "합계"
    ws["B3"] = "=SUM(B2:B2)"
    ws.merge_cells("A5:B5")
    ws["A5"] = "비고"
    path = tmp_path / "경비.xlsx"
    wb.save(str(path))
    return path
