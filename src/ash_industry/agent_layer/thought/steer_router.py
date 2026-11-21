"""[agent_layer] SteerRouter: 뒤에서 작업이 도는 동안 온 말이 그 작업에 대한 지시인지 새 요청인지 작은 모델로 가른다."""

import json
import asyncio
from dataclasses import dataclass

from ash_industry.model_layer.model_types import LLMContext, ModelConfig, StreamOptions, UserMessage
from ash_industry.model_layer.stream import stream_to_message
from ash_industry.common.logger import get_logger

logger = get_logger(__name__)

NEW_REQUEST = "new"
# 판정 한 번. 이보다 오래 걸리면 사용자가 기다리게 하느니 규칙으로 정한다
STEER_TIMEOUT_SEC = 4.0
MESSAGE_MAX_CHARS = 400
LABEL_MAX_CHARS = 80
ACK_MAX_CHARS = 120
# 작은 모델이 선응답을 못 쓰거나 실패했을 때
STEER_ACK = "진행 중인 작업에 반영할게요."

STEER_PROMPT = """\
너는 아래 말투의 비서다. 지금 뒤에서 작업이 돌고 있고, 사용자가 새 말을 보냈다.
그 말이 도는 작업 중 하나에 대한 추가 지시(바꿔, 빼, 더해, 고쳐 등)인지,
그와 상관없는 새 요청이나 질문인지 가려라.

[말투]
{persona}

[도는 작업]
{tasks}

[사용자의 말]
{message}

- 어느 작업에 대한 지시면 target 에 그 작업의 id 를, ack 에 그 작업에 반영하겠다는 말 한 문장을 쓴다
  (무엇을 반영하는지 짧게, 말투를 지켜)
- 새 요청이나 질문이면 target 은 "new", ack 는 빈 문자열
- 애매하면 "new"

JSON 하나만 출력하라: {{"target": "<작업 id>" | "new", "ack": "..."}}
"""


@dataclass(frozen=True)
class SteerDecision:
    """task_id 가 None 이면 새 요청이다. ack 는 그 작업으로 보낼 때 화면에 바로 건넬 말."""

    task_id: str | None
    ack: str = ""


def build_steer_prompt(persona: str, message: str, tasks: list[tuple[str, str]]) -> str:
    lines = "\n".join(f"- {task_id}: {' '.join(label.split())[:LABEL_MAX_CHARS]}" for task_id, label in tasks)
    return STEER_PROMPT.format(
        persona=persona.strip()[:600] or "(정중하고 간결함)", tasks=lines, message=message.strip()[:MESSAGE_MAX_CHARS],
    )


def parse_steer(raw: str, task_ids: list[str]) -> SteerDecision | None:
    """모델 출력에서 판정을 꺼낸다. 형식이 틀리거나 모르는 작업 id 면 None. 순수 함수."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    target = str(payload.get("target", "")).strip()
    if target == NEW_REQUEST:
        return SteerDecision(None)
    if target not in task_ids:
        return None
    ack = " ".join(str(payload.get("ack", "")).split())[:ACK_MAX_CHARS]
    return SteerDecision(target, ack or STEER_ACK)


def fallback_steer(task_ids: list[str]) -> SteerDecision:
    """판정을 못 했을 때. 작업이 하나면 그 작업에 대한 말로 본다. 여럿이면 새 요청."""
    return SteerDecision(task_ids[0], STEER_ACK) if len(task_ids) == 1 else SteerDecision(None)


class SteerRouter:
    """사고 모델에 한 번 묻는다. 실패와 시간 초과는 fallback_steer 로 돌려 호출부가 늘 판정을 받게 한다."""

    def __init__(self, model: ModelConfig, persona: str, timeout_sec: float = STEER_TIMEOUT_SEC) -> None:
        self._model = model
        self._persona = persona
        self._timeout_sec = timeout_sec

    async def route(self, message: str, tasks: list[tuple[str, str]]) -> SteerDecision:
        task_ids = [task_id for task_id, _ in tasks]
        if not task_ids:
            return SteerDecision(None)
        prompt = build_steer_prompt(self._persona, message, tasks)
        try:
            msg = await asyncio.wait_for(
                stream_to_message(self._model, LLMContext(messages=[UserMessage(content=prompt)]), StreamOptions()),
                self._timeout_sec,
            )
        except Exception as exc:
            logger.info(f"[Turn] steer router failed: {exc!r}")
            return fallback_steer(task_ids)
        if msg.error_message:
            logger.info(f"[Turn] steer router failed: {msg.error_message[:200]}")
            return fallback_steer(task_ids)
        return parse_steer(msg.text(), task_ids) or fallback_steer(task_ids)
