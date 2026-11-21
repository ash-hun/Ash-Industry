"""settings 의 자기 재시작: Docker 아래에서만 받고, 응답이 나간 뒤 한 번만 종료를 부른다."""

import asyncio

from ash_industry.ui.web.process_restart import ProcessRestart


async def test_request_schedules_exit_once_after_delay():
    calls: list[str] = []
    restart = ProcessRestart(supervised=lambda: True, exit_=lambda: calls.append("exit"), delay_sec=0)

    first = restart.request()
    second = restart.request()
    await asyncio.sleep(0.01)

    assert (first, second) == (True, True)
    assert calls == ["exit"]


async def test_request_is_refused_outside_a_supervisor():
    calls: list[str] = []
    restart = ProcessRestart(supervised=lambda: False, exit_=lambda: calls.append("exit"), delay_sec=0)

    accepted = restart.request()
    await asyncio.sleep(0.01)

    assert restart.available() is False and accepted is False
    assert calls == []
