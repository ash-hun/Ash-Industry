import pytest
from pathlib import Path
from datetime import datetime

from docs_mcp.docs_paths import DocsPaths, PathOutside


def test_resolve_and_list_stay_inside_root(root: Path) -> None:
    paths = DocsPaths(root)
    assert paths.resolve("sub/a.docx") == root / "sub" / "a.docx"
    assert [d["path"] for d in paths.list_documents()] == ["sub/a.docx"]
    assert [d["path"] for d in paths.list_documents("sub")] == ["sub/a.docx"]
    assert paths.list_documents("nowhere") == []
    out = paths.output_for(root / "sub" / "a.docx", datetime(2026, 1, 2, 3, 4, 5))
    assert out.name == "a.edited-20260102-030405.docx"
    filled = paths.output_for(root / "a.xlsx", datetime(2026, 1, 2, 3, 4, 5), "filled")
    assert filled.name == "a.filled-20260102-030405.xlsx"
    assert paths.render_dir(root / "sub" / "a.docx") == root / ".render" / "a"


@pytest.mark.parametrize("rel", [
    "../x.docx", "/etc/passwd", "~/x.docx", "", "sub/../../x.docx", ".render/b.docx", ".templates/a/schema.json",
    "sub/.hidden/a.docx",
])
def test_resolve_rejects_outside(root: Path, rel: str) -> None:
    with pytest.raises(PathOutside):
        DocsPaths(root).resolve(rel)
