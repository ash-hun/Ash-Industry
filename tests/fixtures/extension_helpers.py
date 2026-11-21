"""확장 로더 테스트용: 도구와 명령을 등록하는 확장 패키지를 임시 디렉터리에 쓴다."""

from pathlib import Path

from ash_industry.core.tools.tools_registry import AshTool, ToolRegistry

EXTENSION_SOURCE = '''
from ash_industry.core.tools.tools_registry import AshTool


class _Tool(AshTool):
    def __init__(self, name):
        self.name, self.description, self.parameters = name, name, {{"type": "object", "properties": {{}}}}


def register(ctx):
    for name in {tools!r}:
        ctx.agent_tools.register(_Tool(name))
    if ctx.memory is not None:
        ctx.agent_tools.register(_Tool({memory_tool!r}))
    if {command!r}:
        async def handle(args, scope):
            return args
        ctx.add_command({command!r}, handle, "test command")
'''


class StubTool(AshTool):
    def __init__(self, name: str) -> None:
        self.name, self.description, self.parameters = name, name, {"type": "object", "properties": {}}


def write_extension(
    root: Path, name: str, tools: tuple[str, ...], memory_tool: str = "", command: str = "", source: str = ""
) -> Path:
    package = root / name
    package.mkdir(parents=True, exist_ok=True)
    body = source or EXTENSION_SOURCE.format(tools=tools, memory_tool=memory_tool or f"{name}_memory", command=command)
    (package / "__init__.py").write_text(body, encoding="utf-8")
    return package


def stub_registry(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    for name in names:
        registry.register(StubTool(name))
    return registry
