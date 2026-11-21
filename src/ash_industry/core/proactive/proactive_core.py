"""[core] proactive 코어. 정책, 채널, push 를 한 객체가 소유하고 Dual-Channel 과 자율 발화를 조율한다."""

import contextlib
from collections.abc import Awaitable, Callable

from ash_industry.core.proactive.policy import SILENT_REASON, DefaultProactivityPolicy, ProactivityPolicy
from ash_industry.core.proactive.proactive_types import ProactiveDecision, ProactiveMessage, ResponsePlan
from ash_industry.agent_layer.thought.thought_types import ProactiveAction, ThoughtFrame
# proactive 발화 운반(fast channel / push, B2). UI에 비동기 전달. 화면에 내보냈으면 True
EmitProactive = Callable[[ProactiveMessage], Awaitable[bool]]
# 저위험 자율 행동 실행기(E2). 실행 후 사람이 읽을 요약을 반환. 보안 게이트는 호출부 책임.
ExecuteActions = Callable[[list[ProactiveAction]], Awaitable[str]]


class ProactivityCore:
    """proactive 동작 코어의 기본 클래스. 정책, 채널, push 를 한 객체가 소유한다.

    독립 class로 격리되어 통째 교체 가능하다. 진입점 2개:
    - plan_request : 요청 턴을 시작하기 전에 사고가 이미 오래 걸린다고 봤는지. 실행은 세션의 TurnDetach 가 한다
    - reflect      : daemon 자율 발화 게이팅 + push (B3)
    기본 구현은 미리 떼어 내지 않고 먼저 말하지 않는다(proactive 를 끈 세션과 같다).
    """

    def plan_request(self, frame: ThoughtFrame | None) -> ResponsePlan:
        return ResponsePlan()

    async def reflect(
        self,
        frame: ThoughtFrame,
        *,
        session_id: str = "default",
        execute: ExecuteActions | None = None,
    ) -> ProactiveDecision:
        return ProactiveDecision(speak=False, reason=SILENT_REASON)

    def check_awaiting(self, session_id: str = "default") -> ProactiveDecision | None:
        return None

    def note_user_activity(self, session_id: str = "default") -> None:
        pass

    def restore_awaiting(self, session_id: str = "default") -> None:
        pass

    def restore_last_spoke(self, session_id: str, seconds_ago: float) -> None:
        pass


class DefaultProactivityCore(ProactivityCore):
    """기본 Dual-Channel 정책 보유자. 협력자(정책, push)는 생성자 주입이라 session/UI와 분리된다.

    요청 턴의 선응답과 뒤로 넘기기는 세션의 TurnDetach 가 한다. 여기서는 사고가 미리 본 계획만 알려 준다.
    """

    def __init__(self, emit_proactive: EmitProactive, policy: ProactivityPolicy | None = None) -> None:
        self._emit = emit_proactive
        self._policy = policy or DefaultProactivityPolicy()

    def plan_request(self, frame: ThoughtFrame | None) -> ResponsePlan:
        # 프레임이 없으면(사고 비활성, 응답 뒤 사고) 미리 정한 것이 없다. 시간으로 정한다
        return self._policy.plan_response(frame) if frame is not None else ResponsePlan()

    async def reflect(
        self,
        frame: ThoughtFrame,
        *,
        session_id: str = "default",
        execute: ExecuteActions | None = None,
    ) -> ProactiveDecision:
        decision = self._policy.decide_proactive(frame, session_id=session_id)
        if not decision.speak:
            return decision

        # E2. 게이팅 통과 시 저위험 자율 행동을 먼저 실행(실행→알림) 후 요약을
        # 메시지에 덧붙인다. execute가 없으면 행동은 건너뛰고 메시지만 push.
        note = ""
        if execute is not None and decision.autonomous_actions:
            with contextlib.suppress(Exception):
                note = await execute(decision.autonomous_actions)

        text = decision.message
        if note:
            text = f"{text}\n{note}" if text else note
        if not text:
            return decision
        if not await self._emit(ProactiveMessage(text=text, kind="proactive")):
            # 답하는 중이거나 집중 중이라 버렸다. 낸 것으로 두면 쿨다운이 걸리고 무시로 세어 임계치가 오른다
            self._policy.withdraw(session_id)
            return ProactiveDecision(speak=False, reason="suppressed")
        return decision

    def check_awaiting(self, session_id: str = "default") -> ProactiveDecision | None:
        return self._policy.check_awaiting(session_id)

    def note_user_activity(self, session_id: str = "default") -> None:
        self._policy.note_user_activity(session_id)

    def restore_awaiting(self, session_id: str = "default") -> None:
        self._policy.restore_awaiting(session_id)

    def restore_last_spoke(self, session_id: str, seconds_ago: float) -> None:
        self._policy.restore_last_spoke(session_id, seconds_ago)
