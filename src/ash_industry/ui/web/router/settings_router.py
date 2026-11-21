"""[ui] 설정 조회, 허용 목록 편집과 즉시 반영, 백엔드 health 와 자기 재시작 REST. Settings 화면과 데스크톱 셸이 쓴다."""

from typing import Any
from pydantic import ValidationError
from fastapi.responses import JSONResponse
from fastapi import APIRouter, HTTPException

from ash_industry.app.settings_overlay import (
    SettingsPatch,
    SettingsOverlay,
    mask_secrets,
    editable_fields,
    editable_values,
    validate_effective,
)
from ash_industry.ui.web.settings_applier import SettingsApplier
from ash_industry.ui.web.process_restart import ProcessRestart
from ash_industry.common.app_version import app_version
from ash_industry.ui.web.web_state import WebState

# 재시작 직전 열린 HUD 전부에 보낸다. 화면은 '연결 끊김 — 재시작 중' 을 보이고 기존 재접속 루프로 돌아온다
RESTARTING_EVENT = "restarting"

SETTINGS_EXAMPLE = {
    "path": "/root/.ash/settings.yaml",
    "fields": {"voice": {"wake_threshold": {
        "title": "Wake Threshold", "type": "number", "minimum": 0.05, "maximum": 0.99}}},
    "editable": {"voice": {"stt_provider": "browser", "wake_threshold": 0.5}},
    "pending": {"voice": {"wake_threshold": 0.7}},
    "effective": {"llm": {"provider": "anthropic", "api_key": "***"}},
}


def pending_changes(stored: dict[str, Any], editable: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """yaml 에는 있지만 지금 프로세스에 아직 반영되지 않은 값. 비어 있지 않으면 백엔드를 다시 띄워야 한다."""
    pending: dict[str, dict[str, Any]] = {}
    for section, values in editable.items():
        saved = stored.get(section)
        if not isinstance(saved, dict):
            continue
        diff = {k: v for k, v in saved.items() if k in values and values[k] != v}
        if diff:
            pending[section] = diff
    return pending


def build_settings_router(
    state: WebState, overlay: SettingsOverlay, applier: SettingsApplier, restart: ProcessRestart
) -> APIRouter:
    router = APIRouter(tags=["settings"])

    def _snapshot() -> dict[str, Any]:
        settings = state.settings
        editable = editable_values(settings)
        return {
            "path": str(overlay.path),
            "fields": editable_fields(),
            "editable": editable,
            "pending": pending_changes(overlay.read(), editable),
            "effective": mask_secrets(settings.model_dump(mode="json")),
        }

    @router.get(
        "/api/health",
        summary="백엔드 상태",
        description="떠 있으면 200 과 패키지 버전. 데스크톱 셸이 백엔드를 띄울지 정할 때 쓴다.",
        responses={200: {"content": {"application/json": {"example": {"ok": True, "version": "0.2.0"}}}}},
    )
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True, "version": app_version()})

    @router.get(
        "/api/settings",
        summary="설정 조회",
        description=(
            "effective 는 지금 프로세스의 전체 적용값(비밀값은 ***), fields 는 고칠 수 있는 항목의 형식과 범위,"
            " editable 은 그 항목의 적용값,"
            " pending 은 settings.yaml 에 저장됐지만 아직 반영되지 않은 값이다."
        ),
        responses={200: {"content": {"application/json": {"example": SETTINGS_EXAMPLE}}}},
    )
    async def get_settings() -> JSONResponse:
        return JSONResponse(_snapshot())

    @router.put(
        "/api/settings",
        summary="설정 편집",
        description=(
            "허용 목록(voice, proactive, thought, focus 의 일부와 shortcuts) 안의 값만 받아"
            " settings.yaml 에 저장하고 바로 반영한다. 모르는 필드, 범위나 형식 밖 값,"
            " 서로 겹치는 단축키는 422. applied 는 바로 반영된 키,"
            " restart_required 가 true 면 restart_keys 는 다시 띄워야 반영된다."
            " 같은 본문을 다시 보내면 changed=false 이고 applied 는 비어 있다."
        ),
        responses={200: {"content": {"application/json": {"example": {
            "changed": True, "applied": ["voice.wake_threshold"], "restart_required": False, "restart_keys": [],
            **SETTINGS_EXAMPLE,
        }}}}},
    )
    async def put_settings(patch: SettingsPatch) -> JSONResponse:
        try:
            validate_effective(state.settings, patch)
            changed = overlay.apply(patch)
        except ValidationError as exc:
            # ctx 의 ValueError 는 JSON 이 안 되고 input 에는 섹션 전체(비밀값 포함)가 든다. msg 에 같은 내용이 있다
            detail = exc.errors(include_url=False, include_context=False, include_input=False)
            raise HTTPException(status_code=422, detail=detail) from exc
        # 파일이 그대로여도(이미 저장된 값) 프로세스가 아직 옛 값이면 쓴다. 같은 값이면 아무것도 안 한다
        applied = await applier.apply(patch)
        return JSONResponse({
            "changed": changed,
            "applied": applied.applied,
            "restart_required": bool(applied.restart_required),
            "restart_keys": applied.restart_required,
            **_snapshot(),
        })

    @router.post(
        "/api/restart",
        summary="백엔드 재시작",
        description=(
            "열린 HUD 전부에 restarting 을 보낸 뒤 프로세스가 정상 종료(exit 0)해 Docker 의 restart 정책이 다시 띄운다."
            " 컨테이너 밖(restart 정책이 없는 곳)에서는 409 로 거절한다."
        ),
        status_code=202,
        responses={
            202: {"content": {"application/json": {"example": {"ok": True, "result": "restarting"}}}},
            409: {"content": {"application/json": {"example": {"ok": False, "result": "no supervisor"}}}},
        },
    )
    async def restart_backend() -> JSONResponse:
        if not restart.available():
            return JSONResponse({"ok": False, "result": "no supervisor"}, status_code=409)
        await state.broadcast_live({"type": RESTARTING_EVENT})
        restart.request()
        return JSONResponse({"ok": True, "result": "restarting"}, status_code=202)

    return router
