"""[ui] Web HUD 기동과 종료: 첫 세션, 스케줄러, 성찰 daemon, 외부 이벤트 폴러, 확장 감시를 켜고 끄고 세션을 저장한다."""

from typing import TYPE_CHECKING
from collections.abc import Awaitable, Callable

from ash_industry.ui.web.web_state import WebState

if TYPE_CHECKING:
    from ash_industry.core.proactive import ProactivityDaemon


class WebLifecycle:
    """FastAPI startup/shutdown 훅이 부른다. start 와 stop 은 한 번씩 짝으로 불린다고 본다."""

    def __init__(self, state: WebState, initial_session_id: str) -> None:
        self._state = state
        self._initial_session_id = initial_session_id
        self._daemon: ProactivityDaemon | None = None
        ctx = state.ctx
        if ctx.scheduler is not None:
            from ash_industry.core.notify import fan_out

            # 화면 방송 + 외부 채널(있으면). 둘 중 하나가 실패해도 다른 쪽은 받는다
            ctx.scheduler.set_notifier(fan_out(state.broadcast_notice, ctx.notifier))
            ctx.scheduler.set_job_board(state.jobs)
            # deliver: conversation 작업(새 공고 등)은 그 에이전트의 대화 세션에 에이전트의 말로 건넨다
            ctx.scheduler.set_conversation(state.converse)

    async def start(self) -> None:
        state, ctx = self._state, self._state.ctx
        # 작업이 돌기 전에 지난 기록을 채워야 runs 가 이어진다
        await state.restore_workflow()
        await state.registry.get_or_create(self._initial_session_id)
        if ctx.scheduler is not None:
            await ctx.scheduler.start()
        await state.loop_lag.start()
        await self._start_daemon()

        # 외부 이벤트 폴러. 소스 YAML 이 없으면 None
        if ctx.external_poller is not None:
            ctx.external_poller.set_job_board(state.jobs)
            await ctx.external_poller.start()
        if ctx.extension_watcher is not None:
            await ctx.extension_watcher.start()

    async def _start_daemon(self) -> None:
        """성찰 daemon: 매 틱 활성 세션 전체를 성찰한다(멀티 세션 추종). 꺼져 있거나 이미 돌면 아무것도 안 한다."""
        state, ctx = self._state, self._state.ctx
        pcfg = state.settings.proactive
        if pcfg.daemon_enabled and self._daemon is None:
            from ash_industry.memory.consolidation.idle import consolidation_targets
            from ash_industry.core.proactive import ProactivityDaemon

            services = state.assembly.services
            consolidate = state.settings.memory.consolidate_on_idle

            def targets() -> list[Callable[[], Awaitable[object]]]:
                sessions = state.registry.sessions_by_recency()
                jobs = state.jobs
                reflects: list[Callable[[], Awaitable[object]]] = [
                    jobs.wrap("proactive:reflect", "proactive", "먼저 말할지 성찰", s.reflect) for s in sessions
                ]
                # 성찰 뒤에 공고화. 같은 틱에서 먼저 말할지 정한 다음 조용히 기억을 정리한다
                if not consolidate:
                    return reflects
                idle_for = services.activity_clock.idle_seconds()
                consolidations = [
                    jobs.wrap("memory:consolidate", "consolidate", "조용할 때 기억 정리", c)
                    for c in consolidation_targets(services.memory, sessions, idle_for, pcfg.daemon_idle_sec)
                ]
                return reflects + consolidations

            self._daemon = ProactivityDaemon(
                targets, interval_sec=pcfg.daemon_interval_sec, trigger=ctx.reflection_trigger
            )
            await self._daemon.start()

    async def _stop_daemon(self) -> None:
        if self._daemon is not None:
            await self._daemon.stop()
            self._daemon = None

    async def restart_daemon(self) -> None:
        """설정 화면이 daemon 설정을 고쳤다. 트리거를 설정대로 다시 만들고 daemon 을 다시 띄운다(끄면 내린다).

        트리거는 만들 때 주기와 유휴 시간을 복사하므로 다시 만든다. 외부 이벤트 트리거는 그대로 섞는다.
        """
        await self._stop_daemon()
        ctx = self._state.ctx
        if ctx.activity_clock is not None:
            from ash_industry.app.infra_builder import InfraBuilder

            ctx.reflection_trigger = InfraBuilder(self._state.settings).build_reflection_trigger(
                ctx.activity_clock, ctx.external_trigger
            )
        await self._start_daemon()

    async def stop(self) -> None:
        state, ctx = self._state, self._state.ctx
        await state.loop_lag.stop()
        await self._stop_daemon()
        if ctx.external_poller is not None:
            await ctx.external_poller.stop()
        if ctx.extension_watcher is not None:
            await ctx.extension_watcher.stop()
        services = state.assembly.services
        await state.registry.consolidate_all_sessions(services.memory)
