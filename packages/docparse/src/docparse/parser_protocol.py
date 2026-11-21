"""[schema] 포맷 어댑터 계약. 포맷을 더할 때는 이 Protocol 을 만족하는 클래스 하나만 더한다."""

from pathlib import Path
from typing import Protocol
from collections.abc import Mapping

from docparse.template.template_schema import AnyLocator, FillValue
from docparse.document_model import Document
from docparse.edit_plan import EditPlan


class FormatAdapter(Protocol):
    """다섯 동작 중 지금은 inspect, replace, fill, to_html 넷. detect_fields 는 빈 양식 탐지 단계에서 더한다."""

    suffixes: tuple[str, ...]

    def inspect(self, path: Path) -> Document:
        """문단, 표, 셀에 id 를 붙여 구조를 돌려준다."""
        ...

    def replace(self, path: Path, plan: EditPlan, out_path: Path) -> Document:
        """계획을 서식을 유지한 채 적용해 out_path 에 저장하고, 저장한 파일을 다시 읽은 구조를 돌려준다."""
        ...

    def fill(self, path: Path, assignments: Mapping[AnyLocator, FillValue], out_path: Path) -> Document:
        """로케이터마다 값을 넣어 out_path 에 저장하고 다시 읽은 구조를 돌려준다. 자리가 없으면 KeyError."""
        ...

    def to_html(self, path: Path) -> str:
        """미리보기용 HTML. 원본 서식과 같지 않다. 본문은 이스케이프한다."""
        ...
