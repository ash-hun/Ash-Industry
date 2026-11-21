"""[mcp] servers.yaml 의 MCP 서버를 자식 프로세스로 띄우고 죽으면 backoff 로 다시 띄우는 런처."""

import os
import sys
import time
import signal
import subprocess
from typing import Any
from pathlib import Path
from dataclasses import field, dataclass

RESTART_BACKOFF_SEC = (2.0, 5.0, 15.0, 30.0)  # 연달아 죽을 때 기다리는 시간. 넘으면 마지막 값
POLL_SEC = 1.0


@dataclass(frozen=True)
class ServerSpec:
    name: str
    command: list[str]
    port: int
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


def expand_env(value: str, environ: dict[str, str]) -> str:
    """"${VAR}" 와 "${VAR:-기본}" 을 environ 으로 채운다. 순수 함수."""
    out = value
    start = out.find("${")
    while start != -1:
        end = out.find("}", start)
        if end == -1:
            break
        token = out[start + 2:end]
        name, _, default = token.partition(":-")
        out = out[:start] + environ.get(name, default) + out[end + 1:]
        start = out.find("${")
    return out


def parse_specs(data: Any, environ: dict[str, str]) -> list[ServerSpec]:
    """YAML 로 읽은 목록을 ServerSpec 으로. 잘못된 항목은 건너뛴다(한 항목이 나머지를 막지 않게)."""
    items = data.get("servers", []) if isinstance(data, dict) else data
    specs: list[ServerSpec] = []
    for item in items or []:
        if not isinstance(item, dict) or not item.get("name") or not item.get("command") or not item.get("port"):
            print(f"[launcher] skipping invalid server entry: {item!r}", flush=True)
            continue
        env = {str(k): expand_env(str(v), environ) for k, v in (item.get("env") or {}).items()}
        specs.append(ServerSpec(
            name=str(item["name"]),
            command=[expand_env(str(c), environ) for c in item["command"]],
            port=int(item["port"]),
            env=env,
            enabled=bool(item.get("enabled", True)),
        ))
    return specs


def backoff_sec(failures: int) -> float:
    return RESTART_BACKOFF_SEC[min(max(failures - 1, 0), len(RESTART_BACKOFF_SEC) - 1)]


class Launcher:
    """서버마다 프로세스 하나. 죽으면 backoff 뒤 다시 띄우고, SIGTERM 이면 전부 내린다."""

    def __init__(self, specs: list[ServerSpec], environ: dict[str, str]) -> None:
        self._specs = [s for s in specs if s.enabled]
        self._environ = environ
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self._failures: dict[str, int] = {}
        self._next_start: dict[str, float] = {}
        self._stopping = False

    def start(self, spec: ServerSpec) -> None:
        env = {**self._environ, **spec.env}
        print(f"[launcher] starting {spec.name} on :{spec.port}: {' '.join(spec.command)}", flush=True)
        self._procs[spec.name] = subprocess.Popen(spec.command, env=env)  # noqa: S603 - 명령은 이미지 안 servers.yaml 에서만 온다

    def tick(self, now: float) -> None:
        for spec in self._specs:
            proc = self._procs.get(spec.name)
            if proc is None:
                if now >= self._next_start.get(spec.name, 0.0):
                    self.start(spec)
                continue
            code = proc.poll()
            if code is None:
                continue
            self._failures[spec.name] = self._failures.get(spec.name, 0) + 1
            wait = backoff_sec(self._failures[spec.name])
            print(f"[launcher] {spec.name} exited with {code}; restarting in {wait:.0f}s", flush=True)
            self._procs.pop(spec.name)
            self._next_start[spec.name] = now + wait

    def stop_all(self) -> None:
        self._stopping = True
        for name, proc in self._procs.items():
            if proc.poll() is None:
                print(f"[launcher] stopping {name}", flush=True)
                proc.terminate()
        deadline = time.monotonic() + 10
        for proc in self._procs.values():
            try:
                proc.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                proc.kill()

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.stop_all())
        signal.signal(signal.SIGINT, lambda *_: self.stop_all())
        while not self._stopping:
            self.tick(time.monotonic())
            time.sleep(POLL_SEC)


def main(argv: list[str]) -> int:
    import yaml

    path = Path(argv[1] if len(argv) > 1 else "servers.yaml")
    with open(path, encoding="utf-8") as f:
        specs = parse_specs(yaml.safe_load(f), dict(os.environ))
    if not specs:
        print(f"[launcher] no servers in {path}", flush=True)
        return 1
    Launcher(specs, dict(os.environ)).run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
