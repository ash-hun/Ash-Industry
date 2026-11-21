"""layers: 패키지 사이 import 가 위 층에서 아래 층으로만 흐르는지 소스를 읽어 확인한다."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "ash_industry"
# 위에서 아래로. 같은 숫자끼리는 서로 불러도 된다(기능 패키지)
RANK = {
    "ui": 5, "app": 4,
    "core": 3, "agent_layer": 3, "memory": 3, "voice": 3, "ion": 3,
    "model_layer": 2, "common": 1, "ash_config": 1,
}


def upward_imports(root: Path) -> list[str]:
    found: list[str] = []
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        top = parts[0].removesuffix(".py")
        if top not in RANK:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("ash_industry."):
                target = node.module.split(".")[1]
                if RANK.get(target, 0) > RANK[top]:
                    found.append(f"{path.relative_to(root)}:{node.lineno} -> {node.module}")
    return found


def test_no_package_imports_a_higher_layer():
    assert upward_imports(ROOT) == []


def test_every_top_level_package_has_a_layer():
    tops = {p.name.removesuffix(".py") for p in ROOT.iterdir() if not p.name.startswith(("_", "."))}

    assert tops - {"py.typed"} <= set(RANK)


def test_upward_import_is_reported(tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "x.py").write_text("from ash_industry.ui.web import server\n", encoding="utf-8")

    assert upward_imports(tmp_path) == ["common/x.py:1 -> ash_industry.ui.web"]
