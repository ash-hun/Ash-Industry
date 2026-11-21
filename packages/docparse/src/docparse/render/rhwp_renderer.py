"""[client] rhwp 로 HWP, HWPX 를 PDF 와 쪽마다 PNG 로 그린다. 외부 프로그램 없이 프로세스 안에서 돈다."""

import importlib
import threading
from typing import Any
from pathlib import Path

from docparse.render.render_service import RenderUnavailable


def load_rhwp() -> Any:
    """그릴 때만 불러온다. 리눅스에서 시스템 FreeType 이 낮으면 네이티브 모듈이 안 열려(CI 실측)
    읽기, 고치기, 채우기까지 막히지 않게 한다."""
    try:
        return importlib.import_module("rhwp")
    except ImportError as exc:
        raise RenderUnavailable(f"rhwp 를 불러오지 못했다: {exc}") from exc


def rhwp_available() -> bool:
    try:
        load_rhwp()
    except RenderUnavailable:
        return False
    return True


class RhwpRenderer:
    """LibreOffice 는 HWPX 를 열지 못해 HWP 계열은 이쪽이 그린다. 한 번에 하나만 그려 CPU 를 독점하지 않는다."""

    def __init__(self, dpi: float = 110.0, max_pages: int = 200) -> None:
        self._dpi = dpi
        self._max_pages = max_pages
        self._lock = threading.Lock()

    def to_pdf(self, path: Path, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{path.stem}.pdf"
        with self._lock:
            data = self._call(lambda: self._parse(path).render_pdf())
        target.write_bytes(data)
        return target

    def to_png(self, path: Path, out_dir: Path) -> list[Path]:
        """pdftoppm 처럼 `<이름>-<쪽>.png`. 같은 원본이면 같은 파일을 덮어쓴다."""
        out_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            doc = self._parse(path)
            pages = [self._call(lambda i=i: doc.render_png(i, dpi=self._dpi)) for i in range(doc.page_count)]
        targets = [out_dir / f"{path.stem}-{i + 1}.png" for i in range(len(pages))]
        for target, data in zip(targets, pages, strict=True):
            target.write_bytes(data)
        return targets

    def _parse(self, path: Path) -> Any:
        # ponytail: 프로세스 안에서 그려 시간 제한이 없다, 큰 문서에서 멈추면 하위 프로세스로 옮긴다
        rhwp = load_rhwp()
        doc = self._call(lambda: rhwp.parse(str(path)))
        if doc.page_count > self._max_pages:
            raise RenderUnavailable(f"쪽이 너무 많다({doc.page_count}쪽, 최대 {self._max_pages})")
        return doc

    def _call(self, fn: Any) -> Any:
        try:
            return fn()
        except (OSError, ValueError, RuntimeError) as exc:
            raise RenderUnavailable(f"rhwp 렌더 실패: {exc}") from exc
