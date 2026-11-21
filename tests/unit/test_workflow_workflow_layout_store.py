"""workflow 의 노드 배치 저장소: 저장과 읽기, 두 번 저장, 범위 밖 값 거부, 없거나 깨진 파일을 검증한다."""

import math
import pytest
from pydantic import ValidationError

from ash_industry.core.workflow.workflow_layout_store import MAX_NODES, WorkflowLayout, WorkflowLayoutStore


def _layout(**nodes: tuple[float, float]) -> WorkflowLayout:
    keyed = {k.replace("_", ":"): {"x": x, "y": y} for k, (x, y) in nodes.items()}
    return WorkflowLayout.model_validate({"nodes": keyed})


def test_save_then_load_returns_same_layout(tmp_path):
    store = WorkflowLayoutStore(str(tmp_path / "sub" / "layout.json"))
    layout = _layout(agent_main=(480.0, 210.5), leaf_main_bash=(370.0, 180.0))

    store.save(layout)

    assert store.load() == layout


def test_saving_same_layout_twice_writes_same_file(tmp_path):
    path = tmp_path / "layout.json"
    store = WorkflowLayoutStore(str(path))
    store.save(_layout(shared_web=(1.0, 2.0), agent_main=(3.0, 4.0)))
    first = path.read_bytes()

    store.save(_layout(agent_main=(3.0, 4.0), shared_web=(1.0, 2.0)))

    assert path.read_bytes() == first
    assert not path.with_suffix(".tmp").exists()


def test_empty_layout_resets(tmp_path):
    store = WorkflowLayoutStore(str(tmp_path / "layout.json"))
    store.save(_layout(agent_main=(1.0, 1.0)))

    store.save(WorkflowLayout())

    assert store.load().nodes == {}


def test_missing_or_broken_file_loads_empty(tmp_path):
    path = tmp_path / "layout.json"
    assert WorkflowLayoutStore(str(path)).load().nodes == {}

    path.write_text("{not json", encoding="utf-8")

    assert WorkflowLayoutStore(str(path)).load().nodes == {}


@pytest.mark.parametrize("x", [math.inf, math.nan, 1e9, -1e9])
def test_out_of_range_coordinates_are_rejected(x):
    with pytest.raises(ValidationError):
        _layout(agent_main=(x, 0.0))


@pytest.mark.parametrize("key", ["", "a" * 201, "agent:\nmain"])
def test_bad_keys_are_rejected(key):
    with pytest.raises(ValidationError):
        WorkflowLayout.model_validate({"nodes": {key: {"x": 0, "y": 0}}})


def test_too_many_nodes_are_rejected():
    nodes = {f"leaf:main:t{i}": {"x": 0, "y": 0} for i in range(MAX_NODES + 1)}

    with pytest.raises(ValidationError):
        WorkflowLayout.model_validate({"nodes": nodes})
