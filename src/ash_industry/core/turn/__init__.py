"""[core] 턴 떼어 내기: 오래 걸리는 턴은 작은 모델의 선응답을 먼저 건네고 뒤에서 이어 돌린 뒤 답을 알린다."""

from ash_industry.core.turn.turn_detach import DetachSettings, Detached, RunningTask, TurnDetach, ack_schedule

__all__ = ["DetachSettings", "Detached", "RunningTask", "TurnDetach", "ack_schedule"]
