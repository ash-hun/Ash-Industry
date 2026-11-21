"""[agent_layer] AckWriter: 오래 걸리는 턴을 뒤로 넘길 때 사용자에게 먼저 건넬 한두 문장을 작은 모델로 쓴다."""

import asyncio

from ash_industry.model_layer.model_types import LLMContext, ModelConfig, UserMessage
from ash_industry.model_layer.stream import stream_to_message
from ash_industry.common.logger import get_logger

logger = get_logger(__name__)

REQUEST_MAX_CHARS = 400
PERSONA_MAX_CHARS = 600
ACK_MAX_CHARS = 200
# 작은 모델이 늦거나 실패했을 때의 선응답. 무엇을 하는지 몰라도 맞는 말만 쓴다
FALLBACK_ACK = "시간이 조금 걸리는 작업이라 뒤에서 이어서 할게요. 끝나면 바로 알려 드릴게요."
# 사용자가 지금 보내기를 눌러 하던 일을 뒤로 넘길 때. 바로 답해야 해서 작은 모델을 기다리지 않는다
SEND_NOW_ACK = "하던 작업은 뒤에서 이어 할게요. 끝나면 알려 드릴게요."

ACK_PROMPT = """\
너는 아래 말투의 비서다. 사용자의 요청을 처리하는 데 시간이 걸려 작업을 뒤에서 이어 하기로 했다.
사용자에게 먼저 건넬 말을 한두 문장으로 써라.

- 무엇을 하고 있는지 요청과 진행 상황에 있는 내용으로만 짧게 말한다. 없는 내용을 지어내지 않는다
- 끝나면 알려 주겠다고 말한다. 걸릴 시간은 말하지 않는다
- 결과나 답을 미리 말하지 않는다. 질문하지 않는다
- 요청과 같은 언어로, 말투를 지켜 쓴다. 따옴표나 머리말 없이 말만 출력한다

[말투]
{persona}

[요청]
{request}

[진행 상황]
{progress}
"""


def build_ack_prompt(persona: str, request: str, progress: str) -> str:
    """작은 모델에 줄 지시문. 입력 길이를 잘라 선응답 호출이 짧게 끝나게 한다."""
    return ACK_PROMPT.format(
        persona=persona.strip()[:PERSONA_MAX_CHARS] or "(정중하고 간결함)",
        request=request.strip()[:REQUEST_MAX_CHARS],
        progress=progress.strip() or "(아직 없음)",
    )


def clean_ack(raw: str) -> str:
    """모델 출력을 선응답으로 다듬는다. 감싼 따옴표를 벗기고 길이를 자른다. 쓸 글이 없으면 빈 문자열."""
    text = " ".join(raw.split()).strip().strip("\"'“”‘’").strip()
    if len(text) > ACK_MAX_CHARS:
        cut = text[:ACK_MAX_CHARS]
        end = max(cut.rfind(mark) for mark in ".!?")
        text = cut[: end + 1] if end > ACK_MAX_CHARS // 2 else cut
    return text


class AckWriter:
    """사고 모델에 한 번 묻는다. 실패하면 None 을 돌려주고, 부른 쪽이 FALLBACK_ACK 를 쓴다."""

    def __init__(self, model: ModelConfig, persona: str) -> None:
        self._model = model
        self._persona = persona

    async def write(self, request: str, progress: str) -> str | None:
        prompt = build_ack_prompt(self._persona, request, progress)
        try:
            msg = await stream_to_message(self._model, LLMContext(messages=[UserMessage(content=prompt)], tools=None))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info(f"[Turn] ack writer failed: {exc!r}")
            return None
        # 프로바이더 오류는 예외가 아니라 빈 메시지의 error_message 로 온다. 남기지 않으면 고정 문장만 보인다
        if msg.error_message:
            logger.info(f"[Turn] ack writer failed: {msg.error_message[:200]}")
            return None
        return clean_ack(msg.text()) or None
