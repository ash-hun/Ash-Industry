"""[core] 도구 결과 글에서 결과물 파일(영상, 음악, 이미지, 문서 렌더)을 찾아 Artifact 로 만드는 순수 규칙."""

import json
from typing import Any, Literal
from pathlib import PurePosixPath
from contextvars import ContextVar

from ash_industry.model_layer.model_types import Artifact

VIDEO = (".mp4", ".webm", ".mov")
AUDIO = (".wav", ".mp3", ".m4a", ".flac", ".ogg")
IMAGE = (".png", ".jpg", ".jpeg", ".webp", ".gif")
# 결과 JSON 에서 파일 경로가 드는 키. 미디어 워커의 잡 결과(output, video, audio)와 스템(stems 값)
PATH_KEYS = ("output", "video", "audio", "clip", "image")
MAX_ARTIFACTS = 6
# docs 서버 render_document 의 결과. 렌더 파일은 문서 폴더의 .render/ 아래에만 생긴다
RENDER_PREFIX = ".render/"
DOCUMENT_PAGES = (".png", ".pdf")
MAX_PAGES = 60

# 맡긴 턴 동안 받는 쪽 도구가 만든 첨부를 모으는 곳. ask_agent 가 열고 결과에 실어 부른 쪽 화면으로 올린다
peer_artifacts: ContextVar["list[Artifact] | None"] = ContextVar("ash_peer_artifacts", default=None)


def collect_peer_artifacts(artifacts: "list[Artifact]") -> None:
    """맡은 턴 안이면 첨부를 모은다. 아니면 아무것도 하지 않는다.

    양식 등록 창(form)은 모으지 않는다. 받는 쪽 도구가 끝날 때 이미 열렸고, 다시 올리면 닫은 창이 또 열린다.
    """
    sink = peer_artifacts.get()
    if sink is not None:
        sink.extend(a for a in artifacts if a.kind != "form")


Kind = Literal["video", "audio", "image"]


def kind_of_path(path: str) -> Kind | None:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in VIDEO:
        return "video"
    if suffix in AUDIO:
        return "audio"
    if suffix in IMAGE:
        return "image"
    return None


def _walk(node: Any, found: list[tuple[Kind, str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in PATH_KEYS and isinstance(value, str):
                kind = kind_of_path(value)
                if kind:
                    found.append((kind, value))
            elif key == "stems" and isinstance(value, dict):
                for stem in value.values():
                    stem_kind = kind_of_path(stem) if isinstance(stem, str) else None
                    if stem_kind and isinstance(stem, str):
                        found.append((stem_kind, stem))
            else:
                _walk(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def artifacts_from_result(text: str, store: str = "creative") -> list[Artifact]:
    """JSON 결과에서 미디어 파일 경로를 모은다. JSON 이 아니거나 없으면 빈 목록. 같은 경로는 한 번. 순수 함수."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, (dict, list)):
        return []
    found: list[tuple[Kind, str]] = []
    _walk(data, found)
    out: list[Artifact] = []
    seen: set[str] = set()
    for kind, path in found:
        if path in seen or path.startswith(("/", "~")) or ".." in path:
            continue
        seen.add(path)
        out.append(Artifact(kind=kind, path=path, title=PurePosixPath(path).name, store=store))
        if len(out) >= MAX_ARTIFACTS:
            break
    return out


def _render_file(path: Any) -> bool:
    if not isinstance(path, str) or not path.startswith(RENDER_PREFIX) or ".." in PurePosixPath(path).parts:
        return False
    return PurePosixPath(path).suffix.lower() in DOCUMENT_PAGES


def document_artifacts(text: str) -> list[Artifact]:
    """render_document 의 png, pdf 결과나 쓰기 도구(apply_edit, fill_template, create_document)의 preview 를
    문서 하나로. 쪽은 받은 순서 그대로, html 과 오류는 빈 목록. 순수 함수."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    preview = data.get("preview")
    return _rendered_document(preview if isinstance(preview, dict) else data)


def form_artifacts(text: str) -> list[Artifact]:
    """detect_fields 결과(path, template_id, candidates)를 양식 등록 창 하나로. 후보가 없으면 빈 목록. 순수 함수."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, dict) or not data.get("candidates") or not data.get("template_id"):
        return []
    path = data.get("path")
    if not isinstance(path, str) or not path or ".." in PurePosixPath(path).parts:
        return []
    return [Artifact(kind="form", path=path, title=PurePosixPath(path).name, store="docs", source=path)]


def docs_artifacts(text: str) -> list[Artifact]:
    """docs 서버 결과에서 화면이 띄울 것. 렌더한 문서나 양식 등록 창. 순수 함수."""
    return document_artifacts(text) or form_artifacts(text)


def _rendered_document(data: dict[str, Any]) -> list[Artifact]:
    if data.get("format") not in ("png", "pdf"):
        return []
    files = data.get("files")
    if not isinstance(files, list):
        return []
    pages = [f for f in files if _render_file(f)][:MAX_PAGES]
    if not pages:
        return []
    raw = data.get("path")
    source = raw if isinstance(raw, str) and raw and ".." not in PurePosixPath(raw).parts else ""
    title = PurePosixPath(source).name if source else PurePosixPath(pages[0]).name
    return [Artifact(kind="document", path=pages[0], title=title, store="docs", pages=pages, source=source)]
