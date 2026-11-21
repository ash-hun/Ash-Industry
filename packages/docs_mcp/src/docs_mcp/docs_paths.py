"""[common] 문서 폴더 안 경로만 허용하고, 결과 파일과 렌더 파일의 자리를 정한다."""

import os
from typing import Any
from pathlib import Path
from datetime import datetime

from docparse import SUPPORTED_SUFFIXES, output_suffix

RENDER_DIR = ".render"
TEMPLATE_DIR = ".templates"


class PathOutside(ValueError):
    """문서 폴더 밖이나 숨김 폴더를 가리켰다."""


class DocsPaths:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def resolve(self, rel: str) -> Path:
        """상대 경로를 폴더 안 절대 경로로. `..`, 절대 경로, `.` 으로 시작하는 이름(.templates 등)은 거부한다."""
        if not rel or rel.startswith(("/", "~")):
            raise PathOutside(f"문서 폴더 안의 상대 경로만 받는다: {rel!r}")
        if any(part.startswith(".") for part in Path(rel).parts):
            raise PathOutside(f"숨김 이름이나 상위 폴더는 받지 않는다: {rel!r}")
        target = (self.root / rel).resolve()
        if not target.is_relative_to(self.root):
            raise PathOutside(f"문서 폴더 밖: {rel!r}")
        # 링크를 따라가 숨김 폴더 안으로 들어가는 것도 막는다
        if any(part.startswith(".") for part in target.relative_to(self.root).parts):
            raise PathOutside(f"숨김 폴더 안: {rel!r}")
        return target

    def relative(self, path: Path) -> str:
        return os.path.relpath(path, self.root)

    def output_for(self, source: Path, when: datetime, label: str = "edited") -> Path:
        """원본 옆에 `<이름>.<label>-<시각>.<확장자>`. 원본은 덮어쓰지 않는다. .hwp 원본의 결과는 .hwpx 다."""
        stamp = when.strftime("%Y%m%d-%H%M%S")
        return source.with_name(f"{source.stem}.{label}-{stamp}{output_suffix(source)}")

    def render_dir(self, source: Path) -> Path:
        return self.root / RENDER_DIR / source.stem

    def template_dir(self) -> Path:
        return self.root / TEMPLATE_DIR

    def list_documents(self, subdir: str = "") -> list[dict[str, Any]]:
        """지원 형식 파일을 이름순으로. 숨김 폴더(.render 등)는 뺀다."""
        base = self.resolve(subdir) if subdir else self.root
        if not base.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for path in sorted(base.rglob("*")):
            parts = path.relative_to(self.root).parts
            if any(p.startswith(".") for p in parts) or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            stat = path.stat()
            out.append({
                "path": self.relative(path), "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            })
        return out
