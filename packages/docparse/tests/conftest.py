"""docparse 테스트가 쓰는 작은 실제 파일. 샘플 양식 대신 코드로 만든다."""

import pytest
from pathlib import Path
from pypdf import PdfWriter
from pptx.util import Inches
from hwpx import HwpxDocument
from openpyxl import Workbook
from pptx import Presentation
from docx import Document as new_docx
from pypdf.generic import (
    NameObject, ArrayObject, FloatObject, NumberObject, StreamObject, TextStringObject, DictionaryObject,
)


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


@pytest.fixture
def form_docx_path(tmp_path: Path) -> Path:
    """채우기용 양식. 자리표시자 하나는 run 셋에 걸쳐 있다."""
    doc = new_docx()
    para = doc.add_paragraph()
    para.add_run("신청자: ").bold = True
    para.add_run("{{이").italic = True
    para.add_run("름}}")
    para.add_run(" 님")
    doc.add_paragraph("소속: 미정")
    doc.add_paragraph("출장 목적")
    doc.add_paragraph("")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "기간"
    table.cell(0, 1).text = "{{기간}}"
    table.cell(1, 0).text = "금액"
    path = tmp_path / "양식.docx"
    doc.save(str(path))
    return path


@pytest.fixture
def form_xlsx_path(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "신청"
    ws["A1"] = "이름"
    ws["B1"] = "{{이름}}"
    ws["A2"] = "금액"
    ws["A3"] = "{{인원}}"
    ws["C1"] = "비고: {{비고}}"
    path = tmp_path / "양식.xlsx"
    wb.save(str(path))
    return path


def _hwpx_form() -> HwpxDocument:
    """굵은 run, run 셋에 걸친 자리표시자, 기준 글, 2x2 표, 병합 칸이 있는 표."""
    doc = HwpxDocument.new()
    doc.paragraphs[0].text = "출장 신청서"
    para = doc.add_paragraph("", include_run=False)
    para.add_run("신청자: ", bold=True)
    para.add_run("{{이", italic=True)
    para.add_run("름}}")
    para.add_run(" 님")
    doc.add_paragraph("성명:")
    doc.add_paragraph("")
    table = doc.add_table(2, 2)
    table.cell(0, 0).text = "기간"
    table.cell(0, 1).text = "{{기간}}"
    table.cell(1, 0).text = "금액"
    merged = doc.add_table(2, 3)
    merged.cell(0, 0).text = "비고"
    merged.merge_cells(0, 1, 0, 2)
    return doc


@pytest.fixture
def hwpx_path(tmp_path: Path) -> Path:
    path = tmp_path / "신청서.hwpx"
    with _hwpx_form() as doc:
        doc.save_to_path(path)
    return path


@pytest.fixture
def hwp_path(tmp_path: Path) -> Path:
    """python-hwpx 가 HWP 5.0 으로 쓴 같은 양식. 한/글이 만든 실제 HWP 는 아니다."""
    path = tmp_path / "신청서.hwp"
    with _hwpx_form() as doc:
        doc.save_to_path(path)
    return path


@pytest.fixture
def pptx_path(tmp_path: Path) -> Path:
    """제목 슬라이드(제목, 부제에 run 셋에 걸친 자리표시자)와 글 상자, 2x2 표가 있는 슬라이드."""
    prs = Presentation()
    first = prs.slides.add_slide(prs.slide_layouts[0])
    first.shapes.title.text = "사업 계획 발표"
    sub = first.placeholders[1].text_frame.paragraphs[0]
    sub.add_run().text = "발표자: "
    sub.add_run().text = "{{발"
    sub.add_run().text = "표자}}"
    second = prs.slides.add_slide(prs.slide_layouts[6])
    box = second.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text_frame
    box.text = "일정"
    box.add_paragraph().text = "둘째 줄"
    table = second.shapes.add_table(2, 2, Inches(1), Inches(3), Inches(4), Inches(1)).table
    table.cell(0, 0).text = "예산"
    table.cell(1, 0).text = "기간"
    table.cell(1, 1).text = "{{기간}}"
    path = tmp_path / "발표.pptx"
    prs.save(str(path))
    return path


def _text_field(name: str, rect: tuple[float, float, float, float]) -> DictionaryObject:
    field = DictionaryObject()
    field.update({
        NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Tx"), NameObject("/T"): TextStringObject(name),
        NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]), NameObject("/F"): NumberObject(4),
    })
    return field


@pytest.fixture
def pdf_form_path(tmp_path: Path) -> Path:
    """글 줄 둘과 글 필드 둘(성명, 신청일자)이 있는 한 쪽 PDF."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    content = StreamObject()
    content.set_data(b"BT /F1 14 Tf 72 780 Td (Leave Request) Tj 0 -30 Td (Name:) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    refs = [writer._add_object(_text_field(n, r)) for n, r in (("name", (120, 740, 300, 760)),
                                                                ("date", (120, 700, 300, 720)))]
    page[NameObject("/Annots")] = ArrayObject(refs)
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject({NameObject("/Fields"): ArrayObject(refs)})
    path = tmp_path / "휴가신청.pdf"
    with open(path, "wb") as f:
        writer.write(f)
    return path
