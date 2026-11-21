"""[service] 빈 양식의 채울 자리를 규칙으로 찾아 필드 후보로 만든다. 순수 함수만."""

import re
import unicodedata
from typing import Literal
from pathlib import PurePath
from pydantic import BaseModel, ConfigDict
from openpyxl.utils import get_column_letter

from docparse.template.template_schema import (
    TEMPLATE_ID, Locator, FieldType, TEXT_FORMATS, TemplateField, SheetCellLocator, TableCellLocator,
    AnchorTextLocator,
)
from docparse.document_model import Cell, Document, Table

Confidence = Literal["high", "low"]
Rule = Literal["table_right", "table_below", "anchor_text", "sheet_right"]

SHORT_LABEL = 20
NAME_MAX = 60
# 기준 글 뒤가 비었거나 밑줄만 있으면 빈 자리다
ANCHOR_LINE = re.compile(r"^\s*(?P<anchor>(?P<label>[^:：{}]{1,40}?)\s*[:：])(?P<rest>[\s_＿]*)$")
SENTENCE_END = (".", "。", "?", "!", "다", "요")
# 앞에 둔 것이 먼저 걸린다. 기간이 날짜보다 먼저다
TYPE_WORDS: tuple[tuple[FieldType, tuple[str, ...]], ...] = (
    ("date_range", ("기간",)),
    ("date", ("일자", "날짜", "생년월일", "일시")),
    ("number", ("금액", "수량", "비용", "개수", "액")),
    ("long_text", ("사유", "내용", "목적", "비고", "요청사항")),
)


class FieldCandidate(BaseModel):
    """탐지한 필드 후보. 사용자가 고친 뒤 name, type, required, locator 를 register_template 에 그대로 넘긴다."""

    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    type: FieldType = "text"
    required: bool = True
    locator: Locator
    rule: Rule
    confidence: Confidence

    def to_field(self) -> TemplateField:
        return TemplateField(name=self.name, type=self.type, required=self.required, locator=self.locator)


def guess_type(label: str) -> FieldType:
    for field_type, words in TYPE_WORDS:
        if any(word in label for word in words):
            return field_type
    return "text"


def field_name(label: str) -> str:
    """글자와 숫자만 남긴다. TemplateField 이름 규칙(\\w)에 맞고 비면 field."""
    kept = "".join(ch for ch in unicodedata.normalize("NFC", label) if ch.isalnum())
    return kept[:NAME_MAX] or "field"


def suggest_template_id(path: str | PurePath) -> str:
    """파일 이름에서 `<이름>-v1`. macOS 파일 이름은 자모가 풀려(NFD) 있어 먼저 합친다."""
    stem = unicodedata.normalize("NFC", PurePath(path).stem)
    base = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", stem).strip("_-")[:61] or "form"
    out = f"{base}-v1"
    if not re.match(TEMPLATE_ID, out):
        return "form-v1"
    return out


def _blank(cell: Cell) -> bool:
    return not cell.text.strip()


def _is_label(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and "{{" not in stripped and any(ch.isalpha() for ch in stripped)


def _confidence(label: str) -> Confidence:
    short = len(label) <= SHORT_LABEL and "\n" not in label and not label.rstrip().endswith(SENTENCE_END)
    return "high" if short else "low"


def _clean_label(text: str) -> str:
    return " ".join(text.split()).rstrip(":：").strip()


def _right_neighbor(row_cells: list[Cell], cell: Cell) -> Cell | None:
    # ponytail: 병합 폭을 몰라 같은 행의 다음 칸을 오른쪽 칸으로 본다(세로 병합에 약함), 걸리면 Cell 에 span
    return next((c for c in row_cells if c.col > cell.col), None)


def _table_candidates(table: Table) -> list[FieldCandidate]:
    rows: dict[int, list[Cell]] = {}
    for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
        rows.setdefault(cell.row, []).append(cell)
    grid = {(c.row, c.col): c for c in table.cells}
    right: list[tuple[Cell, str]] = []
    below: list[tuple[Cell, str]] = []
    for row_cells in rows.values():
        for cell in row_cells:
            if not _is_label(cell.text):
                continue
            label = _clean_label(cell.text)
            neighbor = _right_neighbor(row_cells, cell)
            if neighbor is not None and _blank(neighbor):
                right.append((neighbor, label))
                continue
            # 오른쪽이 자리표시자면 그 칸이 이미 채울 자리다
            if neighbor is not None and "{{" in neighbor.text:
                continue
            under = grid.get((cell.row + 1, cell.col))
            if under is not None and _blank(under):
                below.append((under, label))
    out: list[FieldCandidate] = []
    taken: set[tuple[int, int]] = set()
    # 같은 칸을 두 규칙이 가리키면 오른쪽 규칙이 먼저다
    groups: tuple[tuple[Rule, list[tuple[Cell, str]]], ...] = (("table_right", right), ("table_below", below))
    for rule, pairs in groups:
        for target, label in pairs:
            if (target.row, target.col) in taken:
                continue
            taken.add((target.row, target.col))
            confidence: Confidence = _confidence(label) if rule == "table_right" else "low"
            out.append(FieldCandidate(
                name=field_name(label), label=label, type=guess_type(label),
                locator=TableCellLocator(table=table.index, row=target.row, col=target.col),
                rule=rule, confidence=confidence,
            ))
    return out


def _anchor_candidates(document: Document) -> list[FieldCandidate]:
    """fill 의 anchor_text 는 기준 글이 처음 나온 문단에 쓴다. 그 문단이 이 문단이고 쓸 자리가 비어 있을 때만."""
    out: list[FieldCandidate] = []
    paragraphs = document.paragraphs
    for i, para in enumerate(paragraphs):
        if "{{" in para.text:
            continue
        m = ANCHOR_LINE.match(para.text)
        if m is None or not _is_label(m.group("label")):
            continue
        anchor = m.group("anchor").lstrip()
        if any(anchor in p.text for p in paragraphs[:i]):
            continue
        if not m.group("rest").strip():
            # 뒤가 비면 fill 은 다음 문단을 통째로 바꾼다. 다음 문단이 빈 줄일 때만 안전하다
            following = paragraphs[i + 1] if i + 1 < len(paragraphs) else None
            if following is None or following.text.strip():
                continue
        label = _clean_label(m.group("label"))
        out.append(FieldCandidate(
            name=field_name(label), label=label, type=guess_type(label),
            locator=AnchorTextLocator(after=anchor), rule="anchor_text", confidence=_confidence(label),
        ))
    return out


def _sheet_candidates(table: Table) -> list[FieldCandidate]:
    filled = {(c.row, c.col) for c in table.cells}
    out: list[FieldCandidate] = []
    for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
        # 병합 머리 칸은 범위 폭을 IR 이 몰라 오른쪽 칸이 병합 안일 수 있다
        # ponytail: 병합 라벨은 건너뛰고 병합 안 빈 칸은 못 가린다, 걸리면 Cell 에 span
        if cell.merged or cell.text.startswith("=") or not _is_label(cell.text):
            continue
        if (cell.row, cell.col + 1) in filled:
            continue
        label = _clean_label(cell.text)
        address = f"{get_column_letter(cell.col + 2)}{cell.row + 1}"
        out.append(FieldCandidate(
            name=field_name(label), label=label, type=guess_type(label),
            locator=SheetCellLocator(sheet=table.name, cell=address), rule="sheet_right",
            confidence=_confidence(label),
        ))
    return out


def _dedupe_names(candidates: list[FieldCandidate]) -> list[FieldCandidate]:
    seen: set[str] = set()
    out: list[FieldCandidate] = []
    for cand in candidates:
        name = cand.name
        n = 2
        while name in seen:
            name = f"{cand.name}_{n}"
            n += 1
        seen.add(name)
        out.append(cand if name == cand.name else cand.model_copy(update={"name": name}))
    return out


def detect_fields(document: Document) -> list[FieldCandidate]:
    """본문 기준 글, 표(오른쪽 빈 칸, 아래 빈 칸), XLSX 시트(오른쪽 빈 칸) 순. 같은 문서면 같은 목록과 순서."""
    candidates: list[FieldCandidate] = []
    if document.format == "xlsx":
        for table in document.tables:
            candidates.extend(_sheet_candidates(table))
    elif document.format in TEXT_FORMATS:
        candidates.extend(_anchor_candidates(document))
        for table in document.tables:
            candidates.extend(_table_candidates(table))
    return _dedupe_names(candidates)
