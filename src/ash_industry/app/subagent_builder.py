"""[app] SubagentBuilder: 에이전트 정의 파일의 서브 에이전트 세션과 위임 도구를 조립한다."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ash_industry.core.multi_agent.factory import AgentDefinition, AgentFactory
    from ash_industry.core.tools.tools_registry import ToolRegistry
    from ash_industry.core.multi_agent.tool import AgentNodeTool
    from ash_industry.app.agent_registry import AgentSpec
    from ash_industry.app.app_services import AppServices
    from ash_industry.app.app_context import AppContext
    from ash_industry.core.session import AgentSession


from ash_industry.common.logger import get_logger

logger = get_logger(__name__)


class SubagentBuilder:
    """AgentFactory 가 위임 시점에 부르는 (정의, 세션 id) → 격리된 AgentSession 빌더."""

    def __init__(self, ctx: "AppContext", services: "AppServices", main_registry: "ToolRegistry") -> None:
        self._ctx = ctx
        self._services = services
        self._main_registry = main_registry

    def build_session(self, definition: "AgentDefinition", session_id: str) -> "AgentSession":
        """메모리는 부모의 사용자를 이어받고 에이전트 id 는 자기 이름(inherit_scope).
        memory.ltm 이 False 면 장기 기억 없이. 도구는 정의에 적힌 것만(비어 있으면 메인 전체).
        호출 시점에 고르므로 나중에 등록된 도구(다른 에이전트, orchestrate)도 보인다.
        parent 가 있으면 그 최상위 에이전트의 어투를 지시문 앞에 붙이고, 모델과 기억 범위와 도구 풀을 물려받는다."""
        from ash_industry.core.tools.tools_registry import ToolRegistry
        from ash_industry.model_layer.model_types import ModelConfig
        from ash_industry.core.session import AgentSession

        settings = self._ctx.settings
        parent = self._parent_spec(definition)
        if definition.model_override:
            model = ModelConfig(
                provider=settings.llm.provider,
                model=definition.model_override,
                api_key=settings.llm.api_key.get_secret_value() if settings.llm.api_key else None,
                base_url=settings.llm.base_url,
                temperature=settings.llm.temperature,
                max_tokens=settings.llm.max_tokens,
            )
        elif parent is not None:
            from ash_industry.app.agent_registry import agent_model

            model = agent_model(self._services.model_config, parent.provider, parent.model)
        else:
            model = self._services.model_config
        # 다른 에이전트의 절차는 이름을 적어도 보이지 않는다
        visible = self._main_registry.for_agent(definition.name)
        # 최상위 에이전트 전용 도구(확장이 등록한 것 등)는 agent_tools 에 있다. 부모가 있는 담당만 그 풀을 본다
        pool = self._ctx.agent_tools if parent is not None else None
        if definition.tools or definition.tools_only:
            registry = ToolRegistry()
            for tool_name in definition.tools:
                tool = visible.get(tool_name) or (pool.get(tool_name) if pool is not None else None)
                if tool is not None:
                    registry.register(tool)
        else:
            registry = visible
        system_prompt = definition.system_prompt
        if parent is not None:
            from ash_industry.app.agent_profile import compose_system_prompt

            system_prompt = compose_system_prompt(parent.persona, definition.system_prompt)
        return AgentSession(
            model=model,
            session_id=session_id,
            security_pipeline=self._services.pipeline,
            plugin_runner=self._services.plugin_runner,
            memory=self._services.memory if definition.memory.ltm else None,
            tool_registry=registry,
            skill_registry=self._services.skill_registry,
            session_repo=self._ctx.session_repo,
            system_prompt=system_prompt,
            agent_name=definition.name,
            inherit_scope=True,
            memory_agent=definition.parent,
        )

    def _parent_spec(self, definition: "AgentDefinition") -> "AgentSpec | None":
        """parent 가 가리키는 최상위 에이전트 정의(team/<id>.yaml). 없으면 None 으로 두고 로그만 남긴다."""
        if not definition.parent:
            return None
        from ash_industry.app.agent_registry import load_agent_specs

        spec = load_agent_specs(self._ctx.settings.team.dir).get(definition.parent)
        if spec is None:
            logger.info(f"[SubagentBuilder] '{definition.name}': parent '{definition.parent}' not in team dir")
        return spec

    def node_tool(self, definition: "AgentDefinition", factory: "AgentFactory") -> "AgentNodeTool":
        """정의 → 지연 생성 노드를 감싼 위임 도구. 세션은 첫 위임 때 factory 가 만든다."""
        from ash_industry.core.multi_agent.tool import AgentNodeTool

        tool = AgentNodeTool(definition=definition, factory=factory, memory=self._services.memory)
        # 정의의 설명을 LLM 이 읽는 도구 설명으로 쓴다
        if definition.description:
            tool.description = definition.description
        return tool
