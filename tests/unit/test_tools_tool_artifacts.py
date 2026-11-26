"""tool_artifacts: 도구 결과 JSON 에서 영상, 음악, 이미지 경로를 찾아 Artifact 로 만든다."""

from ash_industry.core.tools.tool_artifacts import (
    docs_artifacts, form_artifacts, kind_of_path, peer_artifacts, document_artifacts, artifacts_from_result,
    collect_peer_artifacts,
)


def test_kind_of_path_by_suffix():
    assert (kind_of_path("a/b.MP4"), kind_of_path("x.wav"), kind_of_path("k.png"), kind_of_path("r.json")) == (
        "video", "audio", "image", None,
    )


def test_artifacts_from_result_walks_nested_json_and_dedupes():
    text = (
        '{"job_id":"j","result":{"output":"out/manim/e2e/Hello.mp4","script":"out/manim/e2e/scene.py",'
        '"stems":{"vocals":"cache/a/vocals.wav","instrumental":"cache/a/inst.wav"},'
        '"video":"out/manim/e2e/Hello.mp4","bad":"/etc/x.mp4","up":"../x.wav"}}'
    )
    found = artifacts_from_result(text)
    assert [(a.kind, a.path, a.title, a.store) for a in found] == [
        ("video", "out/manim/e2e/Hello.mp4", "Hello.mp4", "creative"),
        ("audio", "cache/a/vocals.wav", "vocals.wav", "creative"),
        ("audio", "cache/a/inst.wav", "inst.wav", "creative"),
    ]


def test_artifacts_from_result_ignores_non_json_and_plain_values():
    assert artifacts_from_result("not json") == [] and artifacts_from_result("42") == []
    assert artifacts_from_result('{"output": "report.json"}') == []


def test_document_artifacts_from_render_result():
    text = '{"path": "sub/b.hwpx", "format": "png", "files": [".render/b/b-1.png", ".render/x/../../a.png"]}'
    (doc,) = document_artifacts(text)
    assert (doc.kind, doc.path, doc.title, doc.store) == ("document", ".render/b/b-1.png", "b.hwpx", "docs")
    assert doc.pages == [".render/b/b-1.png"]
    pdf = document_artifacts('{"path": "a.pdf", "format": "pdf", "files": [".render/a/a.pdf"]}')
    assert [d.pages for d in pdf] == [[".render/a/a.pdf"]]


def test_document_artifacts_from_write_tool_preview():
    text = (
        '{"path": "new.docx", "format": "docx", "preview": {"path": "new.docx", "format": "png",'
        ' "files": [".render/new/new-1.png", ".render/new/new-2.png"]}}'
    )
    (doc,) = document_artifacts(text)
    assert (doc.title, doc.pages) == ("new.docx", [".render/new/new-1.png", ".render/new/new-2.png"])
    assert document_artifacts('{"path": "new.docx", "format": "docx", "preview": {"error": "soffice 없음"}}') == []


def test_document_artifacts_ignores_html_errors_and_outside_files():
    assert document_artifacts('{"path": "a.docx", "format": "html", "html": "<p>x</p>"}') == []
    assert document_artifacts('{"error": "LibreOffice 가 없다"}') == []
    assert document_artifacts('{"format": "png", "files": ["a.docx", "/etc/x.png", "sub/a.png"]}') == []
    assert document_artifacts("not json") == []


def test_form_artifacts_from_detect_fields():
    text = '{"path": "uploads/a.docx", "template_id": "a-v1", "format": "docx", "candidates": [{"name": "x"}]}'
    (form,) = docs_artifacts(text)
    assert (form.kind, form.source, form.title) == ("form", "uploads/a.docx", "a.docx")
    assert form_artifacts('{"path": "a.docx", "template_id": "a", "candidates": []}') == []
    assert form_artifacts('{"error": "없는 파일"}') == [] and form_artifacts("not json") == []
    assert form_artifacts('{"path": "../a.docx", "template_id": "a", "candidates": [{"name": "x"}]}') == []


def test_collect_peer_artifacts_leaves_form_to_the_receiver():
    sink: list = []
    token = peer_artifacts.set(sink)
    try:
        collect_peer_artifacts(form_artifacts('{"path": "a.docx", "template_id": "a", "candidates": [{"name": "x"}]}'))
    finally:
        peer_artifacts.reset(token)
    assert sink == []


def test_collect_peer_artifacts_is_noop_outside_a_peer_turn():
    collect_peer_artifacts(artifacts_from_result('{"output": "out/a.mp4"}'))
    assert peer_artifacts.get() is None


def test_collect_peer_artifacts_appends_inside_a_peer_turn():
    sink: list = []
    token = peer_artifacts.set(sink)
    try:
        collect_peer_artifacts(artifacts_from_result('{"output": "out/a.mp4"}'))
    finally:
        peer_artifacts.reset(token)
    assert [a.path for a in sink] == ["out/a.mp4"]
