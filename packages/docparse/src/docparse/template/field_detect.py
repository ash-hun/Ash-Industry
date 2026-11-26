"""[service] 빈 양식의 채울 자리를 규칙으로 찾아 필드 후보로 만든다. 순수 함수만."""

import re
import unicodedata
from typing import Literal
from pathlib import PurePath
from pydantic import BaseModel, ConfigDict
from openpyxl.utils import get_column_letter

from docparse.template.template_schema import (
    TEMPLATE_ID, Locator, FieldType, TEXT_FORMATS, TemplateField, CheckboxLocator, FormFieldLocator, SheetCellLocator,
    TableCellLocator, InlineSlotLocator, AnchorTextLocator,
)
from docparse.template.slot_text import BOXES, box_options, slot_labels
from docparse.document_model import Cell, Document, Paragraph, Table

Confidence = Literal["high", "low"]
Rule = Literal["table_right", "table_below", "anchor_text", "sheet_right", "form_field", "inline_slot", "checkbox"]

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
    options: tuple[str, ...] = ()
    locator: Locator
    rule: Rule
    confidence: Confidence

    def to_field(self) -> TemplateField:
        return TemplateField(
            name=self.name, type=self.type, required=self.required, options=self.options, locator=self.locator,
        )


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
    """체크 칸이 든 글은 라벨이 아니라 채울 자리다."""
    stripped = text.strip()
    return (
        bool(stripped) and "{{" not in stripped and not any(b in stripped for b in BOXES)
        and any(ch.isalpha() for ch in stripped)
    )


def _confidence(label: str) -> Confidence:
    short = len(label) <= SHORT_LABEL and "\n" not in label and not label.rstrip().endswith(SENTENCE_END)
    return "high" if short else "low"


def _clean_label(text: str) -> str:
    return " ".join(text.split()).rstrip(":：").strip()


def _right_neighbor(row_cells: list[Cell], cell: Cell) -> Cell | None:
    """병합 폭 바로 다음 열에서 시작하는 칸. 그 자리가 위에서 내려온 세로 병합에 덮였으면 없다."""
    return next((c for c in row_cells if c.col == cell.col + cell.col_span), None)


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
            under = grid.get((cell.row + cell.row_span, cell.col))
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


def _covered(table: Table) -> set[tuple[int, int]]:
    """병합 범위 안에서 왼쪽 위 칸을 뺀 자리. 이 자리는 값을 쓸 수 없다."""
    out: set[tuple[int, int]] = set()
    for c in table.cells:
        out.update(
            (r, k) for r in range(c.row, c.row + c.row_span) for k in range(c.col, c.col + c.col_span)
            if (r, k) != (c.row, c.col)
        )
    return out


def _sheet_candidates(table: Table) -> list[FieldCandidate]:
    by_pos = {(c.row, c.col): c for c in table.cells}
    covered = _covered(table)
    out: list[FieldCandidate] = []
    for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
        if cell.text.startswith("=") or not _is_label(cell.text):
            continue
        target = (cell.row, cell.col + cell.col_span)
        # 오른쪽이 비었거나 빈 병합 범위의 왼쪽 위 칸이어야 한다
        right = by_pos.get(target)
        if target in covered or (right is not None and right.text.strip()):
            continue
        label = _clean_label(cell.text)
        address = f"{get_column_letter(target[1] + 1)}{cell.row + 1}"
        out.append(FieldCandidate(
            name=field_name(label), label=label, type=guess_type(label),
            locator=SheetCellLocator(sheet=table.name, cell=address), rule="sheet_right",
            confidence=_confidence(label),
        ))
    return out


def _form_candidates(document: Document) -> list[FieldCandidate]:
    """PDF 폼 필드는 이미 채울 자리다. 이름을 라벨로 쓴다. 필드 이름은 만든 사람이 붙였다.
    체크박스와 선택지가 있는 선택 필드는 choice 이고 값은 options 중 하나다."""
    out: list[FieldCandidate] = []
    for item in document.fields:
        if item.kind not in ("text", "choice", "checkbox"):
            continue
        if item.kind == "checkbox" and not item.options:
            continue
        label = item.name.rsplit(".", 1)[-1]
        options = item.options if item.kind != "text" else ()
        out.append(FieldCandidate(
            name=field_name(label), label=label, type="choice" if options else guess_type(label), required=False,
            options=options, locator=FormFieldLocator(name=item.name), rule="form_field", confidence="high",
        ))
    return out


def _scoped_paragraphs(document: Document) -> list[tuple[Paragraph, str]]:
    """본문 문단과 표 칸 안 문단. 칸 안 문단에는 바로 왼쪽 칸의 글을 곁들인다(체크 칸 라벨이 거기 있는 양식)."""
    out: list[tuple[Paragraph, str]] = [(p, "") for p in document.paragraphs]
    for table in document.tables:
        left_of = {(c.row, c.col + c.col_span): c for c in table.cells}
        for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
            left = left_of.get((cell.row, cell.col))
            context = _clean_label(left.text) if left is not None and _is_label(left.text) else ""
            out.extend((p, context) for p in cell.paragraphs)
    return out


def _inline_candidates(document: Document) -> list[FieldCandidate]:
    """`성명(    )` 같은 빈 괄호마다 inline_slot, `□ 예 □ 아니오` 같은 칸 묶음마다 checkbox 후보."""
    slots: list[FieldCandidate] = []
    boxes: list[FieldCandidate] = []
    for para, context in _scoped_paragraphs(document):
        if "{{" in para.text:
            continue
        for label in slot_labels(para.text):
            slots.append(FieldCandidate(
                name=field_name(label), label=label, type=guess_type(label),
                locator=InlineSlotLocator(paragraph=para.id, label=label), rule="inline_slot",
                confidence=_confidence(label),
            ))
        options = tuple(box_options(para.text))
        if not options:
            continue
        head = _clean_label(para.text[: min(para.text.index(b) for b in BOXES if b in para.text)])
        label = head or context or "선택"
        boxes.append(FieldCandidate(
            name=field_name(label), label=label, type="choice", required=len(options) > 1, options=options,
            locator=CheckboxLocator(paragraph=para.id, options=options), rule="checkbox",
            confidence=_confidence(label) if (head or context) else "low",
        ))
    return slots + boxes


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
    """본문 기준 글, 표(오른쪽 빈 칸, 아래 빈 칸), 빈 괄호, 체크 칸, XLSX 시트(오른쪽 빈 칸), PDF 폼 필드 순.
    PPTX 는 표만 본다. 같은 문서면 같은 목록과 순서."""
    candidates: list[FieldCandidate] = []
    if document.format == "pdf":
        candidates.extend(_form_candidates(document))
    elif document.format == "pptx":
        for table in document.tables:
            candidates.extend(_table_candidates(table))
    elif document.format == "xlsx":
        for table in document.tables:
            candidates.extend(_sheet_candidates(table))
    elif document.format in TEXT_FORMATS:
        candidates.extend(_anchor_candidates(document))
        for table in document.tables:
            candidates.extend(_table_candidates(table))
        candidates.extend(_inline_candidates(document))
    return _dedupe_names(candidates)
