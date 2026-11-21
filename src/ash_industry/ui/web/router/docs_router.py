"""[ui] 행정문서 폴더의 렌더 결과(쪽 PNG, PDF)를 읽기 전용으로 내주는 REST."""

from fastapi import APIRouter
from fastapi import Path as PathParam
from pathlib import Path, PurePosixPath
from fastapi.responses import FileResponse, JSONResponse, Response

from ash_industry.core.tools.tool_artifacts import RENDER_PREFIX, DOCUMENT_PAGES
from ash_industry.ui.web.web_state import WebState

MEDIA_TYPES = {".png": "image/png", ".pdf": "application/pdf"}


def resolve_render(root: Path, rel: str) -> Path | None:
    """문서 폴더의 .render/ 안 png, pdf 만. 원본 문서와 템플릿, 밖으로 나가는 경로는 None. 순수 함수."""
    text = rel.strip()
    if not text.startswith(RENDER_PREFIX) or PurePosixPath(text).suffix.lower() not in DOCUMENT_PAGES:
        return None
    base = (root.expanduser() / RENDER_PREFIX).resolve()
    path = (root.expanduser() / text).resolve()
    if base not in path.parents or not path.is_file():
        return None
    return path


def build_docs_router(state: WebState) -> APIRouter:
    router = APIRouter(tags=["docs"])
    root = Path(state.settings.docs.dir)

    @router.get(
        "/api/docs/files/{path:path}",
        summary="문서 렌더 파일",
        description=(
            "행정문서 폴더(ASH_DOCS__DIR, 기본 /data/documents, 읽기 전용 마운트)의 .render/ 아래 쪽 PNG 와 PDF."
            " docs MCP 서버의 render_document 결과를 HUD 문서 창이 받는다. 경로는 폴더 기준 상대 경로이고"
            " .render/ 밖이거나 png, pdf 가 아니면 404. 원본 문서는 내주지 않는다."
        ),
        response_class=Response,
        responses={
            200: {"content": {"image/png": {}, "application/pdf": {}}}, 404: {"content": {"application/json": {}}},
        },
    )
    async def render_file(path: str = PathParam(description="문서 폴더 기준 상대 경로(.render/...)")) -> Response:
        found = resolve_render(root, path)
        if found is None:
            return JSONResponse({"error": f"no such render: {path}"}, status_code=404)
        return FileResponse(found, media_type=MEDIA_TYPES[found.suffix.lower()])

    return router
