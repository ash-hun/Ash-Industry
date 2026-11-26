"""[ui] 채팅 첨부파일을 받아 uploads/(24시간 보관)에 저장하고 id 와 경로를 돌려주는 REST."""

import time
from pathlib import Path
from fastapi.responses import JSONResponse
from fastapi import File, APIRouter, UploadFile

from ash_industry.app.upload_store import MAX_BYTES, UploadStore, UploadTooLarge
from ash_industry.ui.web.web_state import WebState

CHUNK = 1024 * 1024
UPLOAD_EXAMPLE = {
    "id": "3f2a9c1d0b7e", "name": "출장신청서.hwpx", "path": "uploads/3f2a9c1d0b7e-출장신청서.hwpx",
    "size": 48213, "mime": "application/octet-stream", "kind": "document",
}


def build_upload_router(state: WebState) -> APIRouter:
    router = APIRouter(tags=["uploads"])
    store = UploadStore(Path(state.settings.docs.dir))

    @router.post(
        "/api/uploads",
        summary="채팅 첨부파일 올리기",
        description=(
            "multipart/form-data 의 file 하나를 uploads/<내용 해시 12자>-<이름> 에 저장한다(호스트 임시 폴더,"
            " 마지막으로 올린 뒤 24시간이 지나면 지운다)."
            " 형식은 가리지 않고 50MB 까지. 같은 내용을 다시 올리면 같은 id 와 경로를 돌려주고 파일을 더 만들지 않는다."
            " 받은 id 를 ws user_message 의 attachments 에 넣어 보낸다."
        ),
        responses={
            200: {"content": {"application/json": {"example": UPLOAD_EXAMPLE}}},
            413: {"description": "50MB 초과"}, 422: {"description": "file 이 없다"},
        },
    )
    async def upload(file: UploadFile = File(...)) -> JSONResponse:
        chunks: list[bytes] = []
        total = 0
        # 끝까지 받은 뒤 재지 않고 받는 동안 센다. 큰 파일이 메모리를 다 쓰기 전에 끊는다
        while chunk := await file.read(CHUNK):
            total += len(chunk)
            if total > MAX_BYTES:
                return JSONResponse({"error": f"파일이 너무 크다(최대 {MAX_BYTES:,}바이트)"}, status_code=413)
            chunks.append(chunk)
        # 기한이 지난 것을 먼저 치운다. 정리 주기를 기다리지 않아도 올릴 때마다 줄어든다
        store.purge(time.time(), state.settings.docs.upload_ttl_hours * 3600)
        try:
            saved = store.save(file.filename or "file", chunks, file.content_type or "")
        except UploadTooLarge as exc:
            return JSONResponse({"error": str(exc)}, status_code=413)
        return JSONResponse(saved.as_dict())

    return router
