"""[core] MCP 정책 YAML 파일을 읽고 쓰는 저장소. 없으면 기본 정책, 쓰기는 임시 파일 뒤 교체."""

import os
import yaml
from pathlib import Path

from ash_industry.core.policy.mcp_policy import McpPolicy, parse_policy, policy_to_dict

DEFAULT_PATH = "~/.ash/mcp_policy.yaml"


class McpPolicyStore:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self._path = Path(path).expanduser()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> McpPolicy:
        """파일이 없거나 비면 기본 정책. 틀린 파일은 ValueError 로 올려 기동 때 알린다."""
        if not self._path.exists():
            return McpPolicy()
        with open(self._path, encoding="utf-8") as f:
            return parse_policy(yaml.safe_load(f))

    def save(self, policy: McpPolicy) -> None:
        """같은 정책을 두 번 저장해도 파일은 같다. 중간에 죽어도 원본이 남는다."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(policy_to_dict(policy), f, allow_unicode=True, sort_keys=True)
        os.replace(tmp, self._path)
