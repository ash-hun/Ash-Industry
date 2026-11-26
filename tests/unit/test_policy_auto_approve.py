"""policy: auto_approve 저장소가 에이전트별 켜짐을 파일에 남기고 다시 읽으며 깨진 파일은 모두 꺼짐으로 보는지 검증."""

from ash_industry.core.policy.auto_approve import AutoApproveStore


def test_set_persists_and_repeats_safely(tmp_path):
    path = tmp_path / "auto.yaml"
    store = AutoApproveStore(str(path))
    store.set("evi", True)
    store.set("evi", True)
    store.set("main", False)

    assert AutoApproveStore(str(path)).all() == {"evi": True}
    store.set("evi", False)
    assert AutoApproveStore(str(path)).enabled("evi") is False


def test_broken_or_odd_file_means_everything_off(tmp_path):
    path = tmp_path / "auto.yaml"
    path.write_text("agents: [unclosed")
    assert AutoApproveStore(str(path)).all() == {}
    path.write_text("agents: {evi: yes-please, karen: true}")
    assert AutoApproveStore(str(path)).all() == {"karen": True}
