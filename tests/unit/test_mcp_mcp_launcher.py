"""mcp 기능의 컨테이너 런처: 환경변수 치환, 서버 목록 해석, backoff 와 재시작 판단을 검증한다."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location(
    "mcp_launcher", Path(__file__).resolve().parents[2] / "mcp" / "mcp_launcher.py"
)
assert _spec is not None and _spec.loader is not None
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)


def test_expand_env_fills_vars_and_defaults():
    env = {"A": "x"}
    assert launcher.expand_env("${A}-${B:-dflt}-${C}", env) == "x-dflt-"
    assert launcher.expand_env("plain", env) == "plain"


def test_parse_specs_reads_entries_and_skips_broken_ones():
    data = {"servers": [
        {"name": "google", "command": ["workspace-mcp", "--port", "${PORT:-8000}"], "port": 8000,
         "env": {"KEY": "${SECRET}"}},
        {"name": "broken", "port": 1},
        {"name": "off", "command": ["x"], "port": 2, "enabled": False},
    ]}
    specs = launcher.parse_specs(data, {"SECRET": "s"})

    assert [(s.name, s.port, s.enabled) for s in specs] == [("google", 8000, True), ("off", 2, False)]
    assert specs[0].command == ["workspace-mcp", "--port", "8000"] and specs[0].env == {"KEY": "s"}


def test_backoff_grows_and_caps():
    assert [launcher.backoff_sec(n) for n in (0, 1, 2, 3, 4, 9)] == [2.0, 2.0, 5.0, 15.0, 30.0, 30.0]


def test_launcher_restarts_a_dead_server_after_backoff(monkeypatch):
    started: list[str] = []
    procs: list[SimpleNamespace] = []

    def popen(command, env):  # type: ignore[no-untyped-def]
        started.append(command[0])
        proc = SimpleNamespace(code=None, poll=lambda: procs[-1].code)
        procs.append(proc)
        return proc

    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    spec = launcher.ServerSpec(name="g", command=["srv"], port=1)
    run = launcher.Launcher([spec, launcher.ServerSpec(name="off", command=["no"], port=2, enabled=False)], {})

    run.tick(0.0)
    assert started == ["srv"]
    procs[-1].code = 1
    run.tick(1.0)
    run.tick(2.0)
    assert started == ["srv"]        # 2초 backoff 안에는 다시 띄우지 않는다
    run.tick(3.5)
    assert started == ["srv", "srv"]
