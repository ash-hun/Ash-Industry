"""[client] rhwp 로 HWP, HWPX 를 PDF 와 쪽마다 PNG 로 그린다(rsvg-convert 가 있으면 SVG 를 거쳐)."""

import shutil
import tempfile
import importlib
import threading
import subprocess
from typing import Any
from pathlib import Path

from docparse.render.render_service import RenderUnavailable

SVG_DPI = 96.0


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
    """LibreOffice 는 HWPX 를 열지 못해 HWP 계열은 이쪽이 그린다. 한 번에 하나만 그려 CPU 를 독점하지 않는다.

    리눅스 컨테이너에서 rhwp 의 PDF, PNG 는 글꼴을 정확한 이름으로만 찾아 한글이 빠진다(2026-11-24 실측).
    rsvg-convert 는 fontconfig 로 대체 글꼴을 찾으므로, 있으면 rhwp 는 SVG 만 만들고 그리기는 그쪽에 맡긴다.
    """

    def __init__(
        self, dpi: float = 110.0, max_pages: int = 200, rsvg: str | None = None, timeout_sec: float = 120.0,
    ) -> None:
        self._dpi = dpi
        self._max_pages = max_pages
        self._rsvg = rsvg if rsvg is not None else shutil.which("rsvg-convert")
        self._timeout = timeout_sec
        self._lock = threading.Lock()

    def to_pdf(self, path: Path, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{path.stem}.pdf"
        with self._lock:
            doc = self._parse(path)
            if self._rsvg:
                with tempfile.TemporaryDirectory(dir=out_dir) as work:
                    svgs = self._svgs(doc, Path(work))
                    self._run([self._rsvg, "-f", "pdf", "-o", str(target), *map(str, svgs)])
                return target
            data = self._call(lambda: doc.render_pdf())
        target.write_bytes(data)
        return target

    def to_png(self, path: Path, out_dir: Path) -> list[Path]:
        """pdftoppm 처럼 `<이름>-<쪽>.png`. 같은 원본이면 같은 파일을 덮어쓴다."""
        out_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            doc = self._parse(path)
            targets = [out_dir / f"{path.stem}-{i + 1}.png" for i in range(doc.page_count)]
            if self._rsvg:
                zoom = f"{self._dpi / SVG_DPI:.4f}"
                with tempfile.TemporaryDirectory(dir=out_dir) as work:
                    for svg, target in zip(self._svgs(doc, Path(work)), targets, strict=True):
                        self._run([self._rsvg, "-f", "png", "-z", zoom, "-o", str(target), str(svg)])
                return targets
            pages = [self._call(lambda i=i: doc.render_png(i, dpi=self._dpi)) for i in range(doc.page_count)]
        for target, data in zip(targets, pages, strict=True):
            target.write_bytes(data)
        return targets

    def _parse(self, path: Path) -> Any:
        # ponytail: rhwp 파싱은 프로세스 안이라 시간 제한이 없다, 큰 문서에서 멈추면 하위 프로세스로 옮긴다
        rhwp = load_rhwp()
        doc = self._call(lambda: rhwp.parse(str(path)))
        if doc.page_count > self._max_pages:
            raise RenderUnavailable(f"쪽이 너무 많다({doc.page_count}쪽, 최대 {self._max_pages})")
        return doc

    def _svgs(self, doc: Any, work: Path) -> list[Path]:
        svgs = [work / f"{i + 1}.svg" for i in range(doc.page_count)]
        for i, svg in enumerate(svgs):
            svg.write_text(self._call(lambda i=i: doc.render_svg(i)), encoding="utf-8")
        return svgs

    def _run(self, cmd: list[str]) -> None:
        try:
            done = subprocess.run(cmd, capture_output=True, timeout=self._timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RenderUnavailable(f"{cmd[0]} 실행 실패: {exc}") from exc
        if done.returncode != 0:
            raise RenderUnavailable(f"rsvg-convert 실패: {done.stderr.decode(errors='replace')[-300:]}")

    def _call(self, fn: Any) -> Any:
        try:
            return fn()
        except (OSError, ValueError, RuntimeError) as exc:
            raise RenderUnavailable(f"rhwp 렌더 실패: {exc}") from exc
