from docparse import Cell, Document, EditPlan, Paragraph, Replacement, Table, TemplateSchema, verify_edit, verify_fill


def _doc(p0: str = "가", cell: str = "값", inner: str = "값", extra: bool = True) -> Document:
    paragraphs = [Paragraph(id="p0", text=p0)]
    if extra:
        paragraphs.append(Paragraph(id="p1", text="나"))
    cells = (Cell(id="t0r0c0", row=0, col=0, text=cell, paragraphs=(Paragraph(id="t0r0c0p0", text=inner),)),)
    return Document(
        path="a.docx", format="docx", paragraphs=tuple(paragraphs),
        tables=(Table(id="t0", index=0, rows=1, cols=1, cells=cells),),
    )


def test_verify_ok_when_only_targets_and_their_cells_change() -> None:
    plan = EditPlan(replacements=(Replacement(target="p0", text="다"), Replacement(target="t0r0c0", text="새")))
    result = verify_edit(_doc(), _doc(p0="다", cell="새", inner="새"), plan)
    assert result.ok and result.changed == ("p0", "t0r0c0", "t0r0c0p0")


def test_verify_flags_wrong_text_outside_change_missing_ids_and_placeholders() -> None:
    plan = EditPlan(replacements=(Replacement(target="p0", text="다"),))
    after = _doc(p0="{{다}}", cell="바뀜", inner="바뀜", extra=False)
    result = verify_edit(_doc(), after, plan)
    assert not result.ok
    assert result.issues == (
        "계획과 다른 글: p0", "사라진 항목 1개: p1", "계획 밖이 바뀜: t0r0c0, t0r0c0p0", "자리표시자가 남음: p0",
    )


def _fill_schema() -> TemplateSchema:
    return TemplateSchema.model_validate({
        "template_id": "a-v1", "format": "docx", "kind": "blank_form", "source_hash": "h", "fields": [
            {"name": "이름", "locator": {"kind": "placeholder", "token": "{{이름}}"}},
            {"name": "값", "locator": {"kind": "table_cell", "table": 0, "row": 0, "col": 0}},
        ],
    })


def test_verify_fill_ok_when_values_in_place() -> None:
    result = verify_fill(_doc(p0="이름: 홍길동", cell="새", inner="새"), _fill_schema(), {"이름": "홍길동", "값": "새"})
    assert result.ok and result.changed == ("이름", "값")


def test_verify_fill_flags_leftover_token_wrong_cell_and_bad_values() -> None:
    result = verify_fill(_doc(p0="이름: {{이름}}"), _fill_schema(), {"이름": "홍길동", "값": "새"})
    assert result.issues == ("자리표시자가 남음: {{이름}} (p0)", "값이 제자리에 없음: 값")
    assert verify_fill(_doc(), _fill_schema(), {"이름": "홍길동"}).issues == ("빠진 필수 필드: 값",)
