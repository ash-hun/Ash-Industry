from docparse import Cell, Document, EditPlan, Paragraph, Replacement, Table, verify_edit


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
