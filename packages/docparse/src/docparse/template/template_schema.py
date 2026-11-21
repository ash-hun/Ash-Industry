"""[schema] 양식 템플릿의 필드와 채울 자리, 값 검사와 글로 바꾸기. 순수 함수만."""

import re
import math
from datetime import date
from typing import Any, Literal, Annotated
from collections.abc import Mapping, Sequence
from pydantic import Field, BaseModel, ConfigDict, field_validator, model_validator

from docparse.document_model import Document, cell_id

TOKEN = re.compile(r"\{\{(\w+)\}\}")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_RANGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})$")
INTEGER = re.compile(r"^-?\d+$")
TEMPLATE_ID = r"^[0-9A-Za-z가-힣_-]{1,64}$"

FieldType = Literal["text", "long_text", "date", "date_range", "number"]
FillValue = str | int | float


class TemplateValueError(ValueError):
    """채울 값이 스키마에 맞지 않는다. issues 에 항목별 문제."""

    def __init__(self, issues: Sequence[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = tuple(issues)


class PlaceholderLocator(BaseModel):
    """본문이나 셀 안의 `{{이름}}` 글자를 값으로 바꾼다."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["placeholder"] = "placeholder"
    token: str = Field(pattern=r"^\{\{\w+\}\}$")


class TableCellLocator(BaseModel):
    """DOCX 표의 셀 하나를 통째로 값으로 바꾼다. 0부터 센다."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["table_cell"] = "table_cell"
    table: int = Field(ge=0)
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class AnchorTextLocator(BaseModel):
    """DOCX 문단에서 after 글자 뒤. 뒤에 글이 있으면 그 글을, 없으면 다음 문단을 바꾼다."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["anchor_text"] = "anchor_text"
    after: str = Field(min_length=1, max_length=200)


class SheetCellLocator(BaseModel):
    """XLSX 시트의 A1 주소 칸. 빈 칸이어도 쓴다."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["sheet_cell"] = "sheet_cell"
    sheet: str = Field(min_length=1, max_length=31)
    cell: str = Field(pattern=r"^[A-Z]{1,3}[1-9]\d{0,6}$")

    @field_validator("cell", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


AnyLocator = PlaceholderLocator | TableCellLocator | AnchorTextLocator | SheetCellLocator
Locator = Annotated[AnyLocator, Field(discriminator="kind")]


class TemplateField(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^\w+$", max_length=64)
    type: FieldType = "text"
    required: bool = True
    max_chars: int | None = Field(default=None, ge=1)
    max_lines: int | None = Field(default=None, ge=1)
    locator: Locator


class TemplateSchema(BaseModel):
    """origin 은 등록할 때 원본의 문서 폴더 기준 상대 경로. 파서는 쓰지 않고 결과 파일 자리를 정할 때만 쓴다."""

    model_config = ConfigDict(frozen=True)

    template_id: str = Field(pattern=TEMPLATE_ID)
    format: Literal["docx", "xlsx"]
    kind: Literal["placeholder", "blank_form"]
    source_hash: str
    fields: tuple[TemplateField, ...] = Field(min_length=1)
    origin: str = ""

    @model_validator(mode="after")
    def _unique_names(self) -> "TemplateSchema":
        names = [f.name for f in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("필드 이름이 겹친다")
        return self

    def field(self, name: str) -> TemplateField | None:
        return next((f for f in self.fields if f.name == name), None)


def scan_placeholders(document: Document) -> list[str]:
    """문단과 셀 글의 `{{이름}}` 을 처음 나온 순서로 한 번씩."""
    names: list[str] = []
    for text in document.texts().values():
        for name in TOKEN.findall(text):
            if name not in names:
                names.append(name)
    return names


def schema_from_placeholders(
    template_id: str, document: Document, source_hash: str, hints: Sequence[Mapping[str, Any]] = (),
    origin: str = "",
) -> TemplateSchema:
    """찾은 자리표시자마다 text 필드 하나. hints 는 이름이 같은 필드의 type, required, max_chars 등을 덮는다."""
    names = scan_placeholders(document)
    if not names:
        raise ValueError("문서에 자리표시자({{이름}})가 없다. 빈 양식이면 blank_form 과 fields 로 등록한다")
    by_name = {str(h.get("name", "")): h for h in hints}
    unknown = [n for n in by_name if n not in names]
    if unknown:
        raise ValueError(f"문서에 없는 자리표시자: {', '.join(unknown)}")
    fields = tuple(
        TemplateField.model_validate({
            "name": name, "locator": {"kind": "placeholder", "token": f"{{{{{name}}}}}"},
            **{k: v for k, v in by_name.get(name, {}).items() if k != "name"},
        })
        for name in names
    )
    return TemplateSchema(
        template_id=template_id, format=document.format, kind="placeholder", source_hash=source_hash,
        fields=fields, origin=origin,
    )


def check_locators(schema: TemplateSchema, document: Document) -> list[str]:
    """필드마다 채울 자리가 문서에 실제로 있는지. 형식에 맞지 않는 로케이터도 문제로 적는다."""
    texts = document.texts()
    issues: list[str] = []
    for item in schema.fields:
        loc = item.locator
        if isinstance(loc, PlaceholderLocator):
            if not any(loc.token in t for t in texts.values()):
                issues.append(f"{item.name}: 문서에 {loc.token} 이 없다")
        elif isinstance(loc, SheetCellLocator):
            if document.format != "xlsx":
                issues.append(f"{item.name}: sheet_cell 은 XLSX 만")
            elif not any(t.name == loc.sheet for t in document.tables):
                issues.append(f"{item.name}: 시트가 없다 {loc.sheet}")
        elif document.format != "docx":
            issues.append(f"{item.name}: {loc.kind} 는 DOCX 만")
        elif isinstance(loc, TableCellLocator):
            table = next((t for t in document.tables if t.index == loc.table), None)
            if table is None or loc.row >= table.rows or loc.col >= table.cols:
                issues.append(f"{item.name}: 표 칸이 없다 {cell_id(loc.table, loc.row, loc.col)}")
        elif not any(loc.after in t for t in texts.values()):
            issues.append(f"{item.name}: 기준 글이 없다 {loc.after!r}")
    return issues


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _parse_date(text: str) -> date | None:
    if not DATE.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    if INTEGER.match(text):
        return int(text)
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _type_issue(item: TemplateField, value: Any) -> str:
    if item.type == "number":
        return "" if _parse_number(value) is not None else "숫자가 아니다"
    if item.type in ("text", "long_text"):
        ok = isinstance(value, str) or (isinstance(value, int | float) and not isinstance(value, bool))
        return "" if ok else "글이 아니다"
    if not isinstance(value, str):
        return "글이 아니다"
    if item.type == "date":
        return "" if _parse_date(value.strip()) else "날짜는 YYYY-MM-DD"
    m = DATE_RANGE.match(value.strip())
    start, end = (_parse_date(m.group(1)), _parse_date(m.group(2))) if m else (None, None)
    if start is None or end is None:
        return "기간은 YYYY-MM-DD ~ YYYY-MM-DD"
    return "" if start <= end else "기간의 시작이 끝보다 늦다"


def validate_values(schema: TemplateSchema, values: Mapping[str, Any]) -> list[str]:
    """모르는 필드, 빠진 필수 필드, 형식, 글자 수와 줄 수를 검사한다. 문제가 없으면 빈 목록."""
    issues = [f"모르는 필드: {name}" for name in values if schema.field(name) is None]
    for item in schema.fields:
        value = values.get(item.name)
        if _blank(value):
            if item.required:
                issues.append(f"빠진 필수 필드: {item.name}")
            continue
        problem = _type_issue(item, value)
        if problem:
            issues.append(f"{item.name}: {problem}")
            continue
        text = render_value(item, value)
        if item.max_chars is not None and len(text) > item.max_chars:
            issues.append(f"{item.name}: {item.max_chars}자를 넘는다({len(text)}자)")
        if item.max_lines is not None and len(text.splitlines()) > item.max_lines:
            issues.append(f"{item.name}: {item.max_lines}줄을 넘는다")
    return issues


def render_value(item: TemplateField, value: Any) -> str:
    """문서에 들어갈 글. 숫자는 쉼표 없이, 기간은 `시작 ~ 끝` 으로 맞춘다. 검사를 통과한 값만 넣는다."""
    if _blank(value):
        return ""
    if item.type == "number":
        number = _parse_number(value)
        if number is None:
            raise ValueError(f"숫자가 아니다: {item.name}")
        return str(number)
    text = str(value).strip()
    if item.type == "date_range":
        m = DATE_RANGE.match(text)
        if m is None:
            raise ValueError(f"기간 형식이 아니다: {item.name}")
        return f"{m.group(1)} ~ {m.group(2)}"
    return text


def typed_value(item: TemplateField, value: Any) -> FillValue:
    """XLSX 칸이 숫자로 남도록 number 필드는 숫자 그대로, 나머지는 render_value 의 글."""
    if item.type == "number" and not _blank(value):
        number = _parse_number(value)
        if number is not None:
            return number
    return render_value(item, value)


def build_assignments(schema: TemplateSchema, values: Mapping[str, Any]) -> dict[AnyLocator, FillValue]:
    """로케이터마다 넣을 값. 비운 선택 필드는 자리표시자만 빈 글로 지우고 나머지 자리는 그대로 둔다."""
    out: dict[AnyLocator, FillValue] = {}
    for item in schema.fields:
        value = values.get(item.name)
        if _blank(value) and not isinstance(item.locator, PlaceholderLocator):
            continue
        out[item.locator] = typed_value(item, value)
    return out
