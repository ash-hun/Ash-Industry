"""[client] LibreOffice headless 로 PDF 를, pdftoppm 으로 PNG 를 만든다. 한 번에 하나만 돌린다."""

import shutil
import threading
import subprocess
from pathlib import Path
from pypdf import PdfReader


class RenderUnavailable(RuntimeError):
    """렌더 프로그램이 없거나 실패했다."""


class LibreOfficeRenderer:
    """soffice 는 프로필 디렉터리를 잠그므로 동시에 두 개를 띄우면 한쪽이 멈춘다. 잠금으로 직렬화한다."""

    def __init__(
        self, soffice: str | None = None, pdftoppm: str | None = None, timeout_sec: float = 120.0,
        profile_dir: Path | None = None,
    ) -> None:
        self._soffice = soffice or shutil.which("soffice") or shutil.which("libreoffice")
        self._pdftoppm = pdftoppm or shutil.which("pdftoppm")
        self._timeout = timeout_sec
        self._profile = profile_dir or Path.home() / ".docparse-lo"
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self._soffice is not None

    def to_pdf(self, path: Path, out_dir: Path) -> Path:
        if self._soffice is None:
            raise RenderUnavailable("LibreOffice(soffice)가 없다")
        out_dir.mkdir(parents=True, exist_ok=True)
        self._profile.mkdir(parents=True, exist_ok=True)
        cmd = [
            self._soffice, f"-env:UserInstallation=file://{self._profile}", "--headless", "--norestore",
            "--convert-to", "pdf", "--outdir", str(out_dir), str(path),
        ]
        with self._lock:
            done = self._run(cmd)
        target = out_dir / f"{path.stem}.pdf"
        if done.returncode != 0 or not target.exists():
            raise RenderUnavailable(f"PDF 변환 실패: {done.stderr.decode(errors='replace')[-300:]}")
        return target

    def to_png(self, pdf: Path, out_dir: Path, dpi: int = 110) -> list[Path]:
        if self._pdftoppm is None:
            raise RenderUnavailable("pdftoppm(poppler)이 없다")
        prefix = out_dir / pdf.stem
        cmd = [self._pdftoppm, "-png", "-r", str(dpi), str(pdf), str(prefix)]
        done = self._run(cmd)
        if done.returncode != 0:
            raise RenderUnavailable(f"PNG 변환 실패: {done.stderr.decode(errors='replace')[-300:]}")
        return sorted(out_dir.glob(f"{pdf.stem}-*.png"))

    def _run(self, cmd: list[str]) -> "subprocess.CompletedProcess[bytes]":
        try:
            return subprocess.run(cmd, capture_output=True, timeout=self._timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RenderUnavailable(f"{cmd[0]} 실행 실패: {exc}") from exc


def page_count(pdf: Path) -> int:
    return len(PdfReader(str(pdf)).pages)
