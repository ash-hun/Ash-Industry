"""[ui] 백엔드가 스스로 정상 종료(exit 0)해 Docker 의 restart 정책이 다시 띄우게 한다."""

import os
import signal
import asyncio
import threading
from pathlib import Path
from collections.abc import Callable

# ponytail: 컨테이너 안이면 restart 정책 아래라고 본다(정책 없이 띄운 컨테이너는 종료가 곧 끝),
# compose 가 정본이 아니게 되면 환경변수로 바꾼다
DOCKER_MARKER = Path("/.dockerenv")
# docker restart 의 t 와 같다. 종료 훅(세션 저장, 기억 정리)이 이보다 길면 그냥 끝낸다
GRACE_SEC = 10.0
# 응답과 '재시작 중' 방송이 나간 뒤 종료 신호를 보낸다
DELAY_SEC = 0.5


def exit_gracefully(grace_sec: float = GRACE_SEC) -> None:
    """uvicorn 에 SIGTERM 을 보내 종료 훅을 돌리고 0 으로 끝난다. grace 를 넘기면 바로 끝낸다(docker stop 과 같다)."""
    hard_stop = threading.Timer(grace_sec, os._exit, args=(0,))
    hard_stop.daemon = True
    hard_stop.start()
    os.kill(os.getpid(), signal.SIGTERM)


class ProcessRestart:
    """restart 정책 아래(Docker)에서만 받는다. 그 밖에서는 종료가 곧 끝이라 거절해 화면이 다른 길을 찾게 한다."""

    def __init__(
        self,
        supervised: Callable[[], bool] = DOCKER_MARKER.exists,
        exit_: Callable[[], None] = exit_gracefully,
        delay_sec: float = DELAY_SEC,
    ) -> None:
        self._supervised = supervised
        self._exit = exit_
        self._delay = delay_sec
        self._requested = False

    def available(self) -> bool:
        return self._supervised()

    def request(self) -> bool:
        """응답이 나간 뒤 종료한다. 두 번 불려도 종료는 한 번이다. 받았으면 True."""
        if not self.available():
            return False
        if not self._requested:
            self._requested = True
            asyncio.get_running_loop().call_later(self._delay, self._exit)
        return True
