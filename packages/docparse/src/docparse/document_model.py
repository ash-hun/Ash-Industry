"""[schema] 포맷과 무관한 문서 구조(IR). 문단, 표, 셀마다 같은 파일을 다시 읽어도 같은 id 가 붙는다."""

from pydantic import BaseModel, ConfigDict, Field


class Run(BaseModel):
    """서식이 같은 글자 묶음. 치환은 첫 run 의 서식을 남긴다."""

    model_config = ConfigDict(frozen=True)

    id: str
    text: str


class Paragraph(BaseModel):
    """editable 이 거짓이면 읽기만 한다(PDF 글 줄, PPTX 노트와 차트). 편집 계획과 자리표시자 찾기에서 빠진다."""

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    runs: tuple[Run, ...] = ()
    style: str = ""
    editable: bool = True


class Cell(BaseModel):
    """표의 셀. row, col 은 0부터. address 는 XLSX 의 'B3' 같은 주소(다른 포맷은 빈 문자열).
    병합된 칸은 왼쪽 위 칸 하나로 싣고 row_span, col_span 에 차지하는 행과 열 수를 적는다."""

    model_config = ConfigDict(frozen=True)

    id: str
    row: int
    col: int
    text: str
    paragraphs: tuple[Paragraph, ...] = ()
    address: str = ""
    merged: bool = False
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)


class Table(BaseModel):
    """표 하나. XLSX 는 시트 하나가 표 하나다(name 이 시트 이름).
    anchor 는 본문에서 이 표 앞에 오는 문단 수다. 화면이 문단 사이에 표를 끼워 그린다(모르면 -1)."""

    model_config = ConfigDict(frozen=True)

    id: str
    index: int
    rows: int
    cols: int
    cells: tuple[Cell, ...] = ()
    name: str = ""
    anchor: int = Field(default=-1, ge=-1)


class FormField(BaseModel):
    """PDF 의 AcroForm 필드 하나. id 는 `f:<이름>`, kind 는 text, checkbox, choice, other. page 는 1부터(모르면 0).
    options 는 체크박스가 받는 값 이름(/Yes, /Off 같은 것)과 선택 필드의 선택지."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    value: str
    kind: str = "text"
    page: int = 0
    options: tuple[str, ...] = ()


class Document(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    format: str
    paragraphs: tuple[Paragraph, ...] = ()
    tables: tuple[Table, ...] = ()
    fields: tuple[FormField, ...] = ()
    meta: dict[str, str] = Field(default_factory=dict)

    def texts(self) -> dict[str, str]:
        """치환 대상이 될 수 있는 id 마다 지금 텍스트. 본문 문단, 셀, 셀 안 문단. 폼 필드는 채우기로만 바꾼다."""
        out: dict[str, str] = {p.id: p.text for p in self.paragraphs if p.editable}
        for table in self.tables:
            for cell in table.cells:
                out[cell.id] = cell.text
                for para in cell.paragraphs:
                    out[para.id] = para.text
        return out

    def readonly_ids(self) -> set[str]:
        return {p.id for p in self.paragraphs if not p.editable}


def paragraph_id(index: int, prefix: str = "") -> str:
    return f"{prefix}p{index}"


def table_id(index: int) -> str:
    return f"t{index}"


def cell_id(table_index: int, row: int, col: int) -> str:
    return f"t{table_index}r{row}c{col}"


def form_field_id(name: str) -> str:
    return f"f:{name}"
