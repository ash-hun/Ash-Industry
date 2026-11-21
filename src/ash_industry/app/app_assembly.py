"""[app] AppAssembly: 기동 한 번의 조립 결과(인프라, 서비스, 에이전트, 세션 빌더)를 묶어 화면에 넘긴다."""

from typing import TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from ash_industry.app.session_builder import SessionBuilder
    from ash_industry.app.agent_registry import AgentRegistry
    from ash_industry.app.agent_profile import AgentProfile
    from ash_industry.app.app_services import AppServices
    from ash_industry.app.app_context import AppContext


@dataclass(frozen=True)
class AppAssembly:
    """화면이 기동 뒤에 쓰는 것들. profile 과 sessions 는 main 몫이고, 에이전트 전체는 agents 에 있다."""

    ctx: "AppContext"
    services: "AppServices"
    profile: "AgentProfile"
    sessions: "SessionBuilder"
    agents: "AgentRegistry"
