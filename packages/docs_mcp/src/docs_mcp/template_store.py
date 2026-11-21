"""[repository] 양식 템플릿과 채우기 기록을 `<문서 폴더>/.templates/<id>/` 에 파일로 보관한다."""

import os
import re
import json
import hashlib
import tempfile
from typing import Any
from pathlib import Path
from collections.abc import Mapping

from docparse.template.template_schema import TEMPLATE_ID
from docparse import TemplateSchema

SCHEMA_FILE = "schema.json"
FILLS_DIR = "fills"


class TemplateConflict(ValueError):
    """같은 id 로 다른 원본을 등록하려 했다."""


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fill_id_for(template_id: str, source_hash: str, values: Mapping[str, Any]) -> str:
    """같은 양식과 같은 값이면 같은 id. 값은 키 순서와 상관없이 같은 JSON 으로 본다."""
    body = json.dumps(
        {"template_id": template_id, "source_hash": source_hash, "values": dict(values)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def _write_atomic(path: Path, data: bytes) -> None:
    """같은 폴더의 임시 파일에 쓰고 이름을 바꿔, 중간에 죽어도 반쯤 쓴 파일이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class TemplateStore:
    """schema.json 이 있어야 등록된 것이다. 원본 사본을 먼저 쓰고 schema.json 을 마지막에 쓴다."""

    def __init__(self, base: Path) -> None:
        self._base = base

    def list_all(self) -> list[TemplateSchema]:
        if not self._base.is_dir():
            return []
        found = (self.get(d.name) for d in sorted(self._base.iterdir()) if re.fullmatch(TEMPLATE_ID, d.name))
        return [s for s in found if s is not None]

    def get(self, template_id: str) -> TemplateSchema | None:
        path = self._dir(template_id) / SCHEMA_FILE
        if not path.is_file():
            return None
        return TemplateSchema.model_validate_json(path.read_text(encoding="utf-8"))

    def source(self, schema: TemplateSchema) -> Path:
        return self._dir(schema.template_id) / f"source.{schema.format}"

    def register(self, schema: TemplateSchema, source: Path) -> tuple[TemplateSchema, bool]:
        """(저장된 스키마, 새로 등록했는가). 같은 id 와 같은 원본이면 있던 것을 그대로 돌려준다."""
        existing = self.get(schema.template_id)
        if existing is not None:
            if existing.source_hash != schema.source_hash:
                tid = schema.template_id
                raise TemplateConflict(f"{tid} 는 다른 원본으로 이미 등록됐다. 새 버전 id(예: {tid}-v2)로 등록한다")
            return existing, False
        _write_atomic(self.source(schema), source.read_bytes())
        _write_atomic(self._dir(schema.template_id) / SCHEMA_FILE, schema.model_dump_json(indent=2).encode())
        return schema, True

    def get_fill(self, template_id: str, fill_id: str) -> dict[str, Any] | None:
        path = self._fill_path(template_id, fill_id)
        if not path.is_file():
            return None
        record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return record

    def put_fill(self, template_id: str, fill_id: str, record: dict[str, Any]) -> dict[str, Any]:
        """있으면 있던 기록을 그대로 돌려주고 새로 쓰지 않는다."""
        existing = self.get_fill(template_id, fill_id)
        if existing is not None:
            return existing
        body = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
        _write_atomic(self._fill_path(template_id, fill_id), body.encode())
        return record

    def _dir(self, template_id: str) -> Path:
        # 도구 인자로 온 id 가 폴더 밖이나 숨김 이름을 가리키지 못하게 스키마와 같은 패턴만 받는다
        if not re.fullmatch(TEMPLATE_ID, template_id):
            raise ValueError(f"템플릿 id 형식이 아니다(글자, 숫자, -, _ 64자까지): {template_id!r}")
        return self._base / template_id

    def _fill_path(self, template_id: str, fill_id: str) -> Path:
        return self._dir(template_id) / FILLS_DIR / f"{fill_id}.json"
