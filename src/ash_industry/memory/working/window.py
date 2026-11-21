"""[memory] 이력을 최근 턴 수와 나이로 자르되 tool_use/tool_result 짝은 가르지 않는 컨텍스트 창."""

from ash_industry.model_layer.model_types import Message


def cut_at_user_boundary(messages: list[Message]) -> list[Message]:
    """첫 user 메시지부터 돌려준다. 앞에 tool_result 나 assistant 가 고아로 남으면 provider 가 거부한다."""
    for i, m in enumerate(messages):
        if m.role == "user":
            return messages[i:]
    return messages


def turn_starts(messages: list[Message]) -> list[int]:
    """턴은 user 메시지 하나와 그 뒤의 답, 도구 호출, 도구 결과다. 각 턴이 시작하는 위치."""
    return [i for i, m in enumerate(messages) if m.role == "user"]


def last_turns(messages: list[Message], turns: int, max_age_ms: int = 0, now_ms: int | None = None) -> list[Message]:
    """최근 turns 턴. max_age_ms 가 양수면 그보다 오래된 턴은 빼되 마지막 턴은 늘 둔다.

    기준 시각은 now_ms, 없으면 마지막 메시지의 시각이다(순수 함수. 호출자가 시각을 넣는다).
    며칠 전 대화가 창에 남으면 "목록 보여줘" 같은 짧은 말이 그 대화로 이어진다. 그 턴은 일화 회상으로만 돌아온다.
    """
    starts = turn_starts(messages)
    out = cut_at_user_boundary(messages) if turns <= 0 or len(starts) <= turns else messages[starts[-turns]:]
    kept = turn_starts(out)
    if max_age_ms <= 0 or not kept:
        return out
    now = out[-1].timestamp if now_ms is None else now_ms
    fresh = [i for i in kept if now - out[i].timestamp <= max_age_ms]
    return out[fresh[0] if fresh else kept[-1]:]
