"""[core] MCP 도구 호출을 정책(서버, 도구, 에이전트)과 도구 종류로 allow, ask, deny 가운데 하나로 판정하는 순수 함수."""

import re
from typing import Any, Literal
from collections.abc import Mapping
from dataclasses import field, dataclass

Mode = Literal["allow", "ask", "deny"]
Kind = Literal["read", "write", "unknown"]
MODES: tuple[Mode, ...] = ("allow", "ask", "deny")
KINDS: tuple[Kind, ...] = ("read", "write", "unknown")
DEFAULT_MODES: dict[Kind, Mode] = {"read": "allow", "write": "ask", "unknown": "ask"}
# 서버가 도구 주석(readOnlyHint, destructiveHint)을 주지 않을 때 이름 앞머리로 읽기와 쓰기를 가른다
READ_PREFIXES = ("get_", "list_", "search_", "query_", "read_", "find_", "fetch_", "describe_", "show_", "lookup_")
WRITE_PREFIXES = (
    "send_", "create_", "delete_", "manage_", "modify_", "update_", "draft_", "batch_", "remove_", "write_",
    "set_", "add_", "move_", "archive_", "trash_", "reply_", "forward_", "insert_", "upload_", "share_",
)
SECRET_PARAM = re.compile(r"(token|secret|password|passwd|api_key|credential)", re.IGNORECASE)
VALUE_MAX = 60  # 승인 창과 기록에 보일 인자 값 길이
MAX_CALLS_PER_HOUR = 10_000


@dataclass(frozen=True)
class ToolPolicy:
    mode: Mode | None = None  # None 이면 종류별 기본값
    lock: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # 인자 고정. 값이 이 밖이면 묻지 않고 거부
    calls_per_hour: int | None = None  # 시간당 허용 호출 수. None 이면 상한 없음


@dataclass(frozen=True)
class AgentPolicy:
    servers: tuple[str, ...] | None = None  # 이 에이전트가 쓸 수 있는 서버. None 이면 전부
    deny: frozenset[str] = frozenset()  # 이 에이전트에게만 막는 도구


@dataclass(frozen=True)
class ServerPolicy:
    tools: Mapping[str, ToolPolicy] = field(default_factory=dict)
    lock: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # 이 서버의 모든 도구에 거는 인자 고정(계정 등)


@dataclass(frozen=True)
class McpPolicy:
    defaults: Mapping[Kind, Mode] = field(default_factory=lambda: dict(DEFAULT_MODES))
    servers: Mapping[str, ServerPolicy] = field(default_factory=dict)
    agents: Mapping[str, AgentPolicy] = field(default_factory=dict)


@dataclass(frozen=True)
class Verdict:
    mode: Mode
    reason: str


def kind_of(tool: str, annotations: Mapping[str, Any] | None = None) -> Kind:
    """도구 주석이 있으면 그것으로, 없으면 이름 앞머리로. 둘 다 아니면 unknown(기본은 묻는다)."""
    if annotations:
        # 와이어 이름(readOnlyHint)과 파이썬 SDK 모델 이름(read_only_hint) 둘 다 받는다
        read_only = annotations.get("readOnlyHint", annotations.get("read_only_hint"))
        destructive = annotations.get("destructiveHint", annotations.get("destructive_hint"))
        if read_only is True:
            return "read"
        if destructive is True or read_only is False:
            return "write"
    name = tool.lower()
    if name.startswith(READ_PREFIXES):
        return "read"
    if name.startswith(WRITE_PREFIXES):
        return "write"
    return "unknown"


def tool_policy(policy: McpPolicy, server: str, tool: str) -> ToolPolicy:
    """도구 정책에 서버 단위 인자 고정을 합친 것. 같은 인자는 도구 쪽이 이긴다."""
    sp = policy.servers.get(server, ServerPolicy())
    tp = sp.tools.get(tool, ToolPolicy())
    if not sp.lock:
        return tp
    return ToolPolicy(mode=tp.mode, lock={**sp.lock, **tp.lock}, calls_per_hour=tp.calls_per_hour)


def lock_violation(lock: Mapping[str, tuple[str, ...]], params: Mapping[str, Any]) -> str:
    """고정한 인자가 허용 값 밖이면 그 설명, 아니면 빈 문자열. 인자가 없으면 서버 기본값이라 보고 넘긴다."""
    for key, allowed in lock.items():
        if key not in params:
            continue
        value = params[key]
        values = value if isinstance(value, list) else [value]
        bad = [str(v) for v in values if str(v) not in allowed]
        if bad:
            return f"{key}={', '.join(bad)} 은 고정 값({', '.join(allowed)}) 밖이다"
    return ""


def decide(
    policy: McpPolicy,
    agent: str,
    server: str,
    tool: str,
    params: Mapping[str, Any],
    kind: Kind,
    calls_last_hour: int = 0,
) -> Verdict:
    """순서: 인자 고정 위반 → 도구 deny → 에이전트 제한 → 시간당 상한 → 도구 mode → 종류별 기본값."""
    tp = tool_policy(policy, server, tool)
    violation = lock_violation(tp.lock, params)
    if violation:
        return Verdict("deny", violation)
    if tp.mode == "deny":
        return Verdict("deny", f"{server}.{tool} 은 정책에서 막혀 있다")
    ap = policy.agents.get(agent)
    if ap is not None:
        if ap.servers is not None and server not in ap.servers:
            return Verdict("deny", f"{agent} 은 {server} 서버를 쓸 수 없다")
        if tool in ap.deny:
            return Verdict("deny", f"{agent} 에게 {tool} 은 막혀 있다")
    if tp.calls_per_hour is not None and calls_last_hour >= tp.calls_per_hour:
        return Verdict("deny", f"{server}.{tool} 시간당 상한 {tp.calls_per_hour} 회를 넘었다")
    mode = tp.mode or policy.defaults.get(kind, DEFAULT_MODES[kind])
    return Verdict(mode, f"{kind} 도구 · {'도구 정책' if tp.mode else '종류 기본값'} {mode}")


def describe_call(server: str, tool: str, params: Mapping[str, Any]) -> str:
    """승인 창과 기록에 보일 한 줄. 비밀값처럼 보이는 인자는 가리고 긴 값은 자른다."""
    parts = []
    for key, value in params.items():
        shown = "***" if SECRET_PARAM.search(str(key)) else str(value)
        if len(shown) > VALUE_MAX:
            shown = shown[: VALUE_MAX - 1] + "…"
        parts.append(f"{key}={shown}")
    return f"{server}.{tool}({', '.join(parts)})"


def parse_policy(data: Any) -> McpPolicy:
    """YAML 이나 JSON 으로 읽은 값을 정책으로. 모르는 mode 나 모양이면 ValueError."""
    if data is None:
        return McpPolicy()
    if not isinstance(data, Mapping):
        raise ValueError("정책은 매핑이어야 한다")
    defaults = dict(DEFAULT_MODES)
    for kind, mode in (data.get("defaults") or {}).items():
        if kind not in KINDS or mode not in MODES:
            raise ValueError(f"defaults 의 {kind}: {mode} 는 모르는 값이다")
        defaults[kind] = mode
    servers: dict[str, ServerPolicy] = {}
    for server, spec in (data.get("servers") or {}).items():
        spec = spec or {}
        if not isinstance(spec, Mapping):
            raise ValueError(f"{server} 정책은 매핑이어야 한다")
        entries = (spec.get("tools") or {}).items()
        servers[str(server)] = ServerPolicy(
            tools={str(t): _parse_tool(str(server), str(t), ts) for t, ts in entries},
            lock=_parse_lock(spec.get("lock")),
        )
    agents: dict[str, AgentPolicy] = {}
    for agent, spec in (data.get("agents") or {}).items():
        spec = spec or {}
        allowed = spec.get("servers")
        agents[str(agent)] = AgentPolicy(
            servers=None if allowed is None else tuple(str(s) for s in allowed),
            deny=frozenset(str(t) for t in spec.get("deny") or []),
        )
    return McpPolicy(defaults=defaults, servers=servers, agents=agents)


def _parse_tool(server: str, tool: str, spec: Any) -> ToolPolicy:
    spec = spec or {}
    if not isinstance(spec, Mapping):
        raise ValueError(f"{server}.{tool} 정책은 매핑이어야 한다")
    mode = spec.get("mode")
    if mode is not None and mode not in MODES:
        raise ValueError(f"{server}.{tool} 의 mode {mode!r} 는 allow, ask, deny 가운데 하나여야 한다")
    limit = spec.get("calls_per_hour")
    bad_limit = not isinstance(limit, int) or isinstance(limit, bool) or not 0 <= limit <= MAX_CALLS_PER_HOUR
    if limit is not None and bad_limit:
        raise ValueError(f"{server}.{tool} 의 calls_per_hour 는 0 에서 {MAX_CALLS_PER_HOUR} 사이 정수여야 한다")
    return ToolPolicy(mode=mode, lock=_parse_lock(spec.get("lock")), calls_per_hour=limit)


def _parse_lock(raw: Any) -> dict[str, tuple[str, ...]]:
    lock = {}
    for key, values in (raw or {}).items():
        items = values if isinstance(values, list) else [values]
        lock[str(key)] = tuple(str(v) for v in items)
    return lock


def policy_to_dict(policy: McpPolicy) -> dict[str, Any]:
    """저장과 API 응답용. parse_policy 와 왕복하면 같은 정책이다."""
    return {
        "defaults": dict(policy.defaults),
        "servers": {
            server: {
                **({"lock": {k: list(v) for k, v in sp.lock.items()}} if sp.lock else {}),
                "tools": {
                    tool: {
                        **({"mode": tp.mode} if tp.mode else {}),
                        **({"lock": {k: list(v) for k, v in tp.lock.items()}} if tp.lock else {}),
                        **({"calls_per_hour": tp.calls_per_hour} if tp.calls_per_hour is not None else {}),
                    }
                    for tool, tp in sp.tools.items()
                },
            }
            for server, sp in policy.servers.items()
        },
        "agents": {
            agent: {
                **({"servers": list(ap.servers)} if ap.servers is not None else {}),
                **({"deny": sorted(ap.deny)} if ap.deny else {}),
            }
            for agent, ap in policy.agents.items()
        },
    }
