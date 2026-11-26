from docparse import Document, EditPlan, Paragraph, Replacement, preview


def _doc() -> Document:
    paragraphs = (Paragraph(id="p0", text="가"), Paragraph(id="p1", text="나"))
    return Document(path="a.docx", format="docx", paragraphs=paragraphs)


def test_preview_lists_changes() -> None:
    pv = preview(_doc(), EditPlan(replacements=(Replacement(target="p0", text="다"),)))
    assert pv.ok and pv.changes[0].model_dump() == {"target": "p0", "before": "가", "after": "다"}


def test_preview_reports_unknown_duplicate_and_noop() -> None:
    plan = EditPlan(replacements=(
        Replacement(target="p9", text="x"), Replacement(target="p1", text="나"),
        Replacement(target="p0", text="다"), Replacement(target="p0", text="라"),
    ))
    pv = preview(_doc(), plan)
    assert not pv.ok and len(pv.changes) == 1
    assert pv.issues == ("없는 대상: p9", "바뀌는 것이 없음: p1", "같은 대상이 두 번: p0")
    assert preview(_doc(), EditPlan()).issues == ("치환 항목이 없음",)


def test_preview_rejects_readonly_paragraph() -> None:
    doc = Document(path="a.pptx", format="pptx", paragraphs=(Paragraph(id="s0np0", text="노트", editable=False),))
    pv = preview(doc, EditPlan(replacements=(Replacement(target="s0np0", text="고침"),)))
    assert pv.issues == ("고칠 수 없는 대상(읽기 전용): s0np0",)
    assert doc.texts() == {}
