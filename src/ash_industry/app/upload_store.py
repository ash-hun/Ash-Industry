"""[service] 채팅 첨부파일을 uploads/ 에 내용 해시 이름으로 두고, 찾고, 보관 기한이 지나면 지우는 저장소."""

import os
import re
import base64
import hashlib
import mimetypes
import unicodedata
from pathlib import Path
from dataclasses import dataclass

UPLOAD_DIR = "uploads"
MAX_BYTES = 50 * 1024 * 1024
# 모델에 그림으로 넘기는 이미지. Anthropic 은 한 장 5MB 까지 받는다
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
NAME_MAX = 80
_UNSAFE = re.compile(r"[^\w.\-가-힣]+")
_ID = re.compile(r"^[0-9a-f]{12}$")


class UploadTooLarge(ValueError):
    """MAX_BYTES 를 넘었다."""


@dataclass(frozen=True)
class Upload:
    id: str  # 내용 sha256 앞 12자
    name: str  # 정리한 원래 이름
    path: str  # 문서 폴더 기준 상대 경로(uploads/<id>-<name>)
    size: int
    mime: str
    kind: str  # image, audio, video, document, other

    def as_dict(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name, "path": self.path, "size": self.size, "mime": self.mime,
                "kind": self.kind}


def safe_name(raw: str) -> str:
    """경로 구분자, 제어 문자, 공백을 '_' 로. 숨김 파일이 되지 않게 앞의 점을 뺀다. 순수 함수."""
    name = unicodedata.normalize("NFC", Path(raw.replace("\\", "/")).name)
    name = _UNSAFE.sub("_", name).strip("._") or "file"
    stem, dot, ext = name.rpartition(".")
    if dot and len(ext) <= 10:
        return f"{stem[: NAME_MAX - len(ext) - 1]}.{ext}"
    return name[:NAME_MAX]


def kind_of(mime: str, name: str) -> str:
    if mime.startswith(("image/", "audio/", "video/")):
        return mime.split("/", 1)[0]
    suffix = Path(name).suffix.lower()
    if mime == "application/pdf" or suffix in {".docx", ".xlsx", ".pptx", ".hwp", ".hwpx", ".pdf", ".txt", ".csv"}:
        return "document"
    return "other"


def describe(uploads: list[Upload]) -> str:
    """메시지 끝에 붙이는 첨부 안내. 경로는 문서 폴더 기준이라 Evi 문서 도구에 그대로 넘긴다. 순수 함수."""
    lines = [f"[첨부] {u.name} | 경로 {u.path}(문서 폴더 기준) | {u.kind} | {u.size:,}바이트" for u in uploads]
    return "\n".join(lines)


class UploadStore:
    """같은 내용은 같은 파일 하나다. 두 번 올려도 다시 쓰지 않는다."""

    def __init__(self, docs_root: Path) -> None:
        self._dir = docs_root.expanduser() / UPLOAD_DIR

    def save(self, raw_name: str, chunks: list[bytes], mime: str = "") -> Upload:
        data = b"".join(chunks)
        if len(data) > MAX_BYTES:
            raise UploadTooLarge(f"파일이 너무 크다({len(data):,}바이트, 최대 {MAX_BYTES:,})")
        name = safe_name(raw_name)
        upload_id = hashlib.sha256(data).hexdigest()[:12]
        if not mime or mime == "application/octet-stream":
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        target = self._dir / f"{upload_id}-{name}"
        if target.exists():
            # 다시 올렸으면 보관 기한을 지금부터 다시 센다
            os.utime(target)
        else:
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.name}.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        return Upload(upload_id, name, f"{UPLOAD_DIR}/{target.name}", len(data), mime, kind_of(mime, name))

    def purge(self, now: float, ttl_sec: float) -> list[str]:
        """마지막으로 올린 지 ttl_sec 이 지난 파일을 지우고 그 이름들. 두 번 불러도 결과 상태는 같다."""
        if not self._dir.is_dir():
            return []
        removed = []
        for path in sorted(self._dir.iterdir()):
            if path.is_file() and now - path.stat().st_mtime >= ttl_sec:
                path.unlink(missing_ok=True)
                removed.append(path.name)
        return removed

    def find(self, upload_id: str) -> Upload | None:
        """id 로 저장한 파일. 형식이 틀린 id 나 uploads/ 밖은 None."""
        if not _ID.match(upload_id) or not self._dir.is_dir():
            return None
        for path in self._dir.glob(f"{upload_id}-*"):
            if path.is_file() and path.resolve().parent == self._dir.resolve():
                name = path.name[len(upload_id) + 1:]
                mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                return Upload(upload_id, name, f"{UPLOAD_DIR}/{path.name}", path.stat().st_size, mime,
                              kind_of(mime, name))
        return None

    def image_base64(self, upload: Upload) -> str | None:
        """모델에 그림으로 넘길 수 있는 이미지면 base64, 아니면 None."""
        if upload.mime not in IMAGE_TYPES or upload.size > MAX_IMAGE_BYTES:
            return None
        return base64.b64encode((self._dir.parent / upload.path).read_bytes()).decode("ascii")
