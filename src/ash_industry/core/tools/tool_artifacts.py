"""[core] 도구 결과 글에서 결과물 파일(영상, 음악, 이미지)을 찾아 Artifact 로 만드는 순수 규칙."""

import json
from typing import Any, Literal
from pathlib import PurePosixPath

from ash_industry.model_layer.model_types import Artifact

VIDEO = (".mp4", ".webm", ".mov")
AUDIO = (".wav", ".mp3", ".m4a", ".flac", ".ogg")
IMAGE = (".png", ".jpg", ".jpeg", ".webp", ".gif")
# 결과 JSON 에서 파일 경로가 드는 키. 미디어 워커의 잡 결과(output, video, audio)와 스템(stems 값)
PATH_KEYS = ("output", "video", "audio", "clip", "image")
MAX_ARTIFACTS = 6


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
