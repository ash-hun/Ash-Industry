"""[ui] 크리에이티브 워크스페이스의 결과물 파일(영상, 음악, 이미지)을 읽기 전용으로 내주는 REST."""

from pathlib import Path
from fastapi import APIRouter
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse, Response

from ash_industry.core.tools.tool_artifacts import kind_of_path
from ash_industry.ui.web.web_state import WebState

MEDIA_TYPES = {
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".flac": "audio/flac", ".ogg": "audio/ogg",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
}


def resolve_media(root: Path, rel: str) -> Path | None:
    """워크스페이스 안의 미디어 파일만. 밖으로 나가거나 미디어가 아니면 None. 순수 함수."""
    text = rel.strip()
    if not text or text.startswith(("/", "~")) or kind_of_path(text) is None:
        return None
    base = root.expanduser().resolve()
    path = (base / text).resolve()
    if base not in path.parents or not path.is_file():
        return None
    return path


def build_creative_router(state: WebState) -> APIRouter:
    router = APIRouter(tags=["creative"])
    root = Path(state.settings.creative.dir)

    @router.get(
        "/api/creative/files/{path:path}",
        summary="크리에이티브 결과물 파일",
        description=(
            "크리에이티브 워크스페이스(ASH_CREATIVE__DIR, 기본 /data/creative) 안의 영상, 음악, 이미지 파일."
            " 미디어 워커의 잡 결과(output, markers 옆 mp4, wav)를 HUD 플레이어 모달이 받는다."
            " 경로는 워크스페이스 기준 상대 경로이고 밖이거나 미디어가 아니면 404."
        ),
        response_class=Response,
        responses={200: {"content": {"video/mp4": {}, "audio/wav": {}}}, 404: {"content": {"application/json": {}}}},
    )
    async def media_file(path: str = PathParam(description="워크스페이스 기준 상대 경로")) -> Response:
        found = resolve_media(root, path)
        if found is None:
            return JSONResponse({"error": f"no such media: {path}"}, status_code=404)
        return FileResponse(found, media_type=MEDIA_TYPES.get(found.suffix.lower(), "application/octet-stream"))

    return router
