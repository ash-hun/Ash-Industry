"""[app] AgentProfile: 에이전트 한 명분의 정체성, 모델, 사고와 proactive 설정, 피드백 학습기."""

from typing import TYPE_CHECKING
from dataclasses import dataclass, replace
from collections.abc import Callable, Iterable

if TYPE_CHECKING:
    from ash_industry.ash_config import BrandConfig, AshSettings, ProactiveConfig, ThoughtConfig
    from ash_industry.core.proactive.proactive_core import EmitProactive, ProactivityCore
    from ash_industry.agent_layer.thought.steer_router import SteerRouter
    from ash_industry.agent_layer.thought.reply import ReplyClassifier
    from ash_industry.core.proactive.feedback import FeedbackLearner
    from ash_industry.model_layer.model_types import ModelConfig
    from ash_industry.core.turn import TurnDetach

# 사고 모델(속생각, 답 분류, 선응답)의 출력 상한. 짧은 JSON 과 한두 문장이라 이것으로 넉넉하다
THOUGHT_MAX_TOKENS = 4096

# 지금은 에이전트가 하나다. 기존 메모리와 세션 데이터가 이 id 로 쌓여 있으므로 바꾸지 않는다
MAIN_AGENT_ID = "main"

# 개성과 상관없이 모든 에이전트가 지킨다. 업무 지시보다 뒤에 둬서 마지막으로 읽히게 한다
ANSWER_RULE = (
    "답은 간결하게 한다. 지시받은 것에 필요한 말만 하고, 묻지 않은 설명, 일반론, 대안, 부연은 붙이지 않는다."
)

# 팀이 둘 이상일 때 모든 에이전트가 지키는 위임 규칙. 담당이 있는 일은 직접 하지 않고 ask_agent 로 맡긴다
TEAM_RULE = (
    "팀 규칙: 요청을 받으면 먼저 아래 팀에서 그 일을 담당하는 에이전트가 있는지 본다."
    " 있으면 직접 하지 않고 ask_agent 로 그 에이전트에게 맡기고, 받은 답을 사용자에게 전한다."
    " 담당이 없는 일만 직접 한다. 다른 에이전트에게서 받은 일은 보낸 에이전트에게 되돌리지 않는다."
)

ProactivityFactory = Callable[["EmitProactive"], "ProactivityCore"]


def compose_system_prompt(persona: str, instructions: str | None) -> str:
    """개성(말투), 업무 지시, 모든 에이전트 공통 답변 규칙 순으로 잇는다."""
    parts = [p.strip() for p in (persona, instructions or "", ANSWER_RULE) if p and p.strip()]
    return "\n\n".join(parts)


def team_rule(agent_id: str, profiles: Iterable["AgentProfile"]) -> str:
    """이 에이전트가 읽을 위임 규칙과 자기를 뺀 팀 명단. 동료가 없으면 빈 문자열. 순수 함수."""
    roster = [
        f"- {p.agent_id}: {p.name}{' (팀 총괄)' if p.is_main else ''}" + (f": {p.description}" if p.description else "")
        for p in profiles if p.agent_id != agent_id
    ]
    if not roster:
        return ""
    return TEAM_RULE + "\n팀:\n" + "\n".join(roster)


@dataclass(frozen=True)
class AgentProfile:
    """에이전트마다 달라질 수 있는 것을 한곳에 모은다. 세션 조립은 이 묶음만 보고 에이전트를 만든다."""

    agent_id: str
    brand: "BrandConfig"
    model: "ModelConfig"
    thought: "ThoughtConfig"
    proactive: "ProactiveConfig"
    feedback_learner: "FeedbackLearner"
    # 아래 셋은 정의 파일에서 온다. main 은 개성만 시스템 프롬프트로 두고 도구는 전체를 쓴다
    description: str = ""
    system_prompt: str | None = None
    tools: tuple[str, ...] = ()
    # 경계. ask 는 스스로 할 때(목표 차례, 스케줄 작업, 먼저 해 두기) 하지 않고 물어야 하는 도구,
    # never 는 어디서도 쓰지 않는 도구. 사용자가 대화로 직접 시킨 일은 이미 물은 것으로 본다
    ask_tools: tuple[str, ...] = ()
    never_tools: tuple[str, ...] = ()

    @property
    def is_main(self) -> bool:
        return self.agent_id == MAIN_AGENT_ID

    @property
    def name(self) -> str:
        """화면과 다른 에이전트가 부르는 이름. 브랜드 워드마크와 같다."""
        return self.brand.name

    def with_team(self, rule: str) -> "AgentProfile":
        """팀 규칙을 시스템 프롬프트 끝에 붙인 사본. 규칙이 비면 그대로. 두 번 붙여도 한 번만 들어간다."""
        if not rule or (self.system_prompt and rule in self.system_prompt):
            return self
        prompt = f"{self.system_prompt}\n\n{rule}" if self.system_prompt else rule
        return replace(self, system_prompt=prompt)

    @classmethod
    def main(
        cls, settings: "AshSettings", model: "ModelConfig", feedback_learner: "FeedbackLearner"
    ) -> "AgentProfile":
        """env 설정에서 기본 에이전트(main)를 만든다."""
        return cls(
            agent_id=MAIN_AGENT_ID,
            brand=settings.brand,
            model=model,
            thought=settings.thought,
            proactive=settings.proactive,
            feedback_learner=feedback_learner,
            system_prompt=compose_system_prompt(settings.brand.persona, None),
        )

    def thought_model(self) -> "ModelConfig":
        """사고 모델: 사고 설정에 지정한 항목만 메인 모델에서 바꾸고 나머지는 이어받는다."""
        return thought_model_config(self.thought, self.model)

    def reply_classifier(self) -> "ReplyClassifier | None":
        """🔔 짧은 답과 음성 승인 답 분류기. 사고가 꺼져 있으면 None(화면은 키워드만 쓴다)."""
        if not self.thought.enabled:
            return None
        from ash_industry.agent_layer.thought.reply import ReplyClassifier

        return ReplyClassifier(self.thought_model())

    def turn_detach(self) -> "TurnDetach | None":
        """Dual-Channel 의 턴 떼어 내기. 시간이 0 이면 None. 사고가 꺼지면 선응답은 고정 문장.

        먼저 말 걸기(proactive.enabled)와 따로 본다. 먼저 말 걸기를 끈 팀 에이전트도 긴 턴은 떼어 낸다.
        """
        pcfg = self.proactive
        if pcfg.detach_after_sec <= 0:
            return None
        from ash_industry.agent_layer.thought.ack_writer import AckWriter
        from ash_industry.core.turn import DetachSettings, TurnDetach

        writer = AckWriter(self.thought_model(), self.brand.persona) if self.thought.enabled else None
        return TurnDetach(DetachSettings(after_sec=pcfg.detach_after_sec, lead_sec=pcfg.ack_lead_sec), writer)

    def steer_router(self) -> "SteerRouter | None":
        """뒤에서 도는 작업에 온 말을 가르는 작은 모델. 사고를 끄면 None 이고 세션은 규칙으로 가른다."""
        if not self.thought.enabled:
            return None
        from ash_industry.agent_layer.thought.steer_router import SteerRouter

        return SteerRouter(self.thought_model(), self.brand.persona)

    def proactivity_factory(self) -> "ProactivityFactory | None":
        """proactive 와 사고가 둘 다 켜져 있을 때만, 세션의 emit 에 묶을 ProactivityCore 팩토리."""
        pcfg = self.proactive
        # 사고가 꺼져 있으면 프레임이 없어 proactivity 가 무의미하다
        if not pcfg.enabled or not self.thought.enabled:
            return None
        from ash_industry.core.proactive import DefaultProactivityCore, DefaultProactivityPolicy

        learner = self.feedback_learner

        def factory(emit: "EmitProactive") -> "ProactivityCore":
            policy = DefaultProactivityPolicy(
                confidence_threshold=pcfg.effective_threshold(),
                cooldown_sec=pcfg.cooldown_sec,
                ignore_after_sec=pcfg.ignore_after_sec,
                awaiting_expire_sec=pcfg.awaiting_expire_sec,
                threshold_provider=learner.threshold,
                cooldown_provider=lambda: pcfg.cooldown_sec,
            )
            return DefaultProactivityCore(emit_proactive=emit, policy=policy)

        return factory


def thought_model_config(tcfg: "ThoughtConfig", main: "ModelConfig") -> "ModelConfig":
    """사고 설정에 지정한 항목만 main 모델에서 바꾼다. 출력 상한은 THOUGHT_MAX_TOKENS 를 넘지 않는다. 순수 함수."""
    from ash_industry.model_layer.model_types import ModelConfig

    api_key = tcfg.api_key.get_secret_value() if tcfg.api_key is not None else main.api_key
    return ModelConfig(
        provider=tcfg.provider or main.provider,
        model=tcfg.model or main.model,
        api_key=api_key,
        base_url=tcfg.base_url or main.base_url,
        temperature=main.temperature,
        # 에이전트가 긴 답용으로 올린 상한(예: 128000)을 그대로 물리면 작은 모델이 400 으로 거절한다(실측)
        max_tokens=min(main.max_tokens, THOUGHT_MAX_TOKENS),
    )
