"""migration: jarvis-agent 상태를 새 이름으로 옮기는 계산과 두 번 돌려도 같은 결과를 검증한다."""

import subprocess
from scripts.migrate_from_jarvis import (
    DockerMigration,
    copy_env,
    copy_home,
    relation_renames,
    rename_env_text,
    volume_plan,
)

OLD_ENV = (
    "JARVIS_LLM__PROVIDER=anthropic\n"
    "# JARVIS_TEAM__DIR=~/.jarvis/team\n"
    "JARVIS_SESSION__POSTGRES_DSN=postgresql://jarvis:jarvis@postgres:5432/jarvis\n"
    "JARVIS_ION__BACKEND_URL=http://jarvis-backend:7777\n"
)


def test_rename_env_text_renames_keys_and_old_names_and_is_stable():
    new = rename_env_text(OLD_ENV)

    assert new == (
        "ASH_LLM__PROVIDER=anthropic\n"
        "# ASH_TEAM__DIR=~/.ash/team\n"
        "ASH_SESSION__POSTGRES_DSN=postgresql://ash:ash@postgres:5432/ash\n"
        "ASH_ION__BACKEND_URL=http://ash-backend:7777\n"
    )
    assert rename_env_text(new) == new


def test_rename_env_text_keeps_unrelated_values():
    assert rename_env_text("TZ=Asia/Seoul\nNOTE=jarvis is fine here\n") == "TZ=Asia/Seoul\nNOTE=jarvis is fine here\n"


def test_relation_renames_maps_kinds_and_skips_existing_targets():
    rows = ["jarvis_sessions:r", "jarvis_sessions_pkey:i", "ash_entries:r", "jarvis_entries:r", "jarvis_seq:S", "x:r"]

    assert relation_renames(rows) == [
        ("SEQUENCE", "jarvis_seq", "ash_seq"),
        ("TABLE", "jarvis_sessions", "ash_sessions"),
        ("INDEX", "jarvis_sessions_pkey", "ash_sessions_pkey"),
    ]


def test_relation_renames_ignores_unsafe_names_and_unknown_kinds():
    assert relation_renames(['jarvis_x";drop:r', "jarvis_fn:f", "broken"]) == []


def test_volume_plan_only_includes_existing_old_volumes():
    existing = ["jarvis_agent_jarvis_data", "jarvis_agent_postgres_data", "other_mcp_data"]

    assert volume_plan(existing, "jarvis_agent", "ash-industry") == [
        ("jarvis_agent_jarvis_data", "ash-industry_ash_data"),
        ("jarvis_agent_postgres_data", "ash-industry_postgres_data"),
    ]


def test_copy_home_copies_once_and_second_run_does_nothing(tmp_path):
    src, dst = tmp_path / ".jarvis", tmp_path / ".ash"
    (src / "sessions").mkdir(parents=True)
    (src / "sessions" / "a.jsonl").write_text("x", encoding="utf-8")

    assert copy_home(src, dst) is True
    (dst / "sessions" / "a.jsonl").write_text("changed", encoding="utf-8")
    assert copy_home(src, dst) is False
    assert (dst / "sessions" / "a.jsonl").read_text(encoding="utf-8") == "changed"


def test_copy_home_recovers_from_a_half_written_copy(tmp_path):
    src, dst = tmp_path / ".jarvis", tmp_path / ".ash"
    src.mkdir()
    (src / "settings.yaml").write_text("a: 1\n", encoding="utf-8")
    (tmp_path / ".ash.migrating").mkdir()

    assert copy_home(src, dst) is True
    assert (dst / "settings.yaml").exists() and not (tmp_path / ".ash.migrating").exists()


def test_copy_env_writes_renamed_file_once_with_private_mode(tmp_path):
    old, new = tmp_path / "old.env", tmp_path / "new.env"
    old.write_text(OLD_ENV, encoding="utf-8")

    assert copy_env(old, new) is True
    assert new.read_text(encoding="utf-8").startswith("ASH_LLM__PROVIDER=")
    assert new.stat().st_mode & 0o777 == 0o600
    assert copy_env(old, new) is False


class FakeDocker:
    def __init__(self, volumes: list[str], filled: set[str]) -> None:
        self.volumes, self.filled, self.calls = volumes, filled, []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        out = ""
        if args[:3] == ["docker", "volume", "ls"]:
            out = "\n".join(self.volumes)
        elif args[:3] == ["docker", "run", "--rm"] and "ls -A /v | head -n 1" in args:
            out = "x" if args[4].split(":")[0] in self.filled else ""
        return subprocess.CompletedProcess(args, 0, out, "")


def test_copy_volumes_skips_new_volumes_that_already_have_data():
    run = FakeDocker(["jarvis_agent_jarvis_data", "jarvis_agent_postgres_data", "ash-industry_ash_data"],
                     filled={"ash-industry_ash_data"})

    done = DockerMigration(run, "jarvis_agent", "ash-industry").copy_volumes(apply=True)

    assert done == ["jarvis_agent_postgres_data -> ash-industry_postgres_data"]
    assert ["docker", "volume", "create", "ash-industry_postgres_data"] in run.calls


def test_copy_volumes_dry_run_does_not_create_anything():
    run = FakeDocker(["jarvis_agent_jarvis_data"], filled=set())

    assert DockerMigration(run, "jarvis_agent", "ash-industry").copy_volumes(apply=False) == [
        "jarvis_agent_jarvis_data -> ash-industry_ash_data"
    ]
    assert not any(c[:3] == ["docker", "volume", "create"] for c in run.calls)
