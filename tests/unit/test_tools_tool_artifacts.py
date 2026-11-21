"""tool_artifacts: 도구 결과 JSON 에서 영상, 음악, 이미지 경로를 찾아 Artifact 로 만든다."""

from ash_industry.core.tools.tool_artifacts import kind_of_path, document_artifacts, artifacts_from_result


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


def test_document_artifacts_ignores_html_errors_and_outside_files():
    assert document_artifacts('{"path": "a.docx", "format": "html", "html": "<p>x</p>"}') == []
    assert document_artifacts('{"error": "LibreOffice 가 없다"}') == []
    assert document_artifacts('{"format": "png", "files": ["a.docx", "/etc/x.png", "sub/a.png"]}') == []
    assert document_artifacts("not json") == []
