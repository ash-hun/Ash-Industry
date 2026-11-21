"""[app] 확장 디렉터리의 파이썬 패키지를 읽어 에이전트 전용 도구와 슬래시 명령을 등록한다."""

import sys
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING
from dataclasses import dataclass, field

from ash_industry.common.logger import get_logger

if TYPE_CHECKING:
    from ash_industry.agent_layer.openloop.openloop_store import OpenLoopStore
    from ash_industry.core.tools.tools_registry import ToolRegistry
    from ash_industry.core.slash.dispatcher import ScopedHandler
    from ash_industry.memory.memory_service import MemoryService

# 확장 이름이 표준 모듈이나 플랫폼 패키지를 덮지 않도록 접두를 붙여 sys.modules 에 넣는다
EXTENSION_MODULE_PREFIX = "ash_ext_"
ENTRY_FUNCTION = "register"

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExtensionCommand:
    """확장이 등록해 달라고 한 슬래시 명령 하나. 디스패처가 만들어진 뒤에 붙는다."""

    name: str
    handler: "ScopedHandler"
    description: str = ""


@dataclass
class ExtensionContext:
    """확장의 register(ctx) 가 받는 것. 플랫폼 내부 객체 중 확장이 써도 되는 것만 둔다."""

    agent_tools: "ToolRegistry"
    memory: "MemoryService | None" = None
    loops: "OpenLoopStore | None" = None
    commands: list[ExtensionCommand] = field(default_factory=list)

    def add_command(self, name: str, handler: "ScopedHandler", description: str = "") -> None:
        self.commands.append(ExtensionCommand(name, handler, description))


class ExtensionLoader:
    """`<dir>/<name>/__init__.py` 마다 register(ctx) 를 부른다. 이름순이라 매번 같은 순서로 등록된다.

    한 확장이 실패해도 로그만 남기고 다음 확장으로 간다. 개인 확장 하나가 플랫폼 기동을 막지 않게 한다.
    """

    def __init__(self, extensions_dir: str) -> None:
        self._dir = Path(extensions_dir).expanduser()

    def load(self, ctx: ExtensionContext) -> list[str]:
        if not self._dir.is_dir():
            return []
        loaded: list[str] = []
        for package in sorted(p for p in self._dir.iterdir() if (p / "__init__.py").is_file()):
            try:
                module = import_extension(package)
                register = getattr(module, ENTRY_FUNCTION, None)
                if register is None:
                    logger.warning("extension_skipped", extension=package.name, reason="no register()")
                    continue
                register(ctx)
                loaded.append(package.name)
            except Exception as exc:
                logger.warning("extension_failed", extension=package.name, error=str(exc))
        if loaded:
            logger.info("extensions_loaded", extensions=loaded)
        return loaded


def import_extension(package: Path) -> object:
    """확장 디렉터리 하나를 ash_ext_<이름> 패키지로 import 한다. 확장 저장소의 테스트도 이 함수로 읽는다."""
    # 패키지로 읽어야 확장 안의 상대 import(from .fetch import ...)가 풀린다
    name = f"{EXTENSION_MODULE_PREFIX}{package.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(
        name, package / "__init__.py", submodule_search_locations=[str(package)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {package}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
