"""[api] docs MCP 서버. 문서 폴더의 파일을 열거, 구조 조회, 편집 계획, 적용, 렌더하는 도구 다섯 개."""

import os
from pathlib import Path
from datetime import datetime
from typing import Any, Literal
from collections.abc import Callable
from mcp.types import ToolAnnotations
from mcp.server.mcpserver import MCPServer

from docparse import EditPlan, Replacement, RenderUnavailable, apply, inspect, preview, render, to_html, verify_edit
from docs_mcp.plan_store import PlanStore, StoredPlan, plan_id_for
from docparse.parser_registry import UnsupportedFormat
from docs_mcp.docs_paths import DocsPaths, PathOutside
from docparse.document_model import Document

MAX_ITEMS = 2000
MAX_FILE_BYTES = 20 * 1024 * 1024
READ = ToolAnnotations(read_only_hint=True, idempotent_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)


def document_dict(doc: Document, include_empty: bool) -> dict[str, Any]:
    """LLM 이 읽는 구조. 빈 문단은 기본으로 빼고, 항목이 너무 많으면 앞부분만 싣고 알린다."""
    paragraphs = [
        {"id": p.id, "text": p.text, **({"style": p.style} if p.style else {})}
        for p in doc.paragraphs if include_empty or p.text.strip()
    ]
    tables: list[dict[str, Any]] = []
    for t in doc.tables:
        cells = [
            {"id": c.id, "row": c.row, "col": c.col, "text": c.text, **({"address": c.address} if c.address else {})}
            for c in t.cells if include_empty or c.text.strip()
        ]
        name = {"name": t.name} if t.name else {}
        tables.append({"id": t.id, **name, "rows": t.rows, "cols": t.cols, "cells": cells})
    out: dict[str, Any] = {"path": doc.path, "format": doc.format, "paragraphs": paragraphs, "tables": tables}
    total = len(paragraphs) + sum(len(t["cells"]) for t in tables)
    if total > MAX_ITEMS:
        out["paragraphs"] = paragraphs[:MAX_ITEMS]
        out["tables"] = []
        out["truncated"] = f"항목 {total}개 중 문단 {MAX_ITEMS}개만. 표는 subdir 로 나눠 보라"
    return out


class DocsService:
    """도구 본체. 시각은 밖에서 넣어 같은 입력이면 같은 결과 파일 이름이 나온다."""

    def __init__(
        self, paths: DocsPaths, plans: PlanStore | None = None, clock: Callable[[], datetime] | None = None,
        renderer: Any = None,
    ) -> None:
        self._paths = paths
        self._plans = plans or PlanStore()
        self._clock = clock or datetime.now
        self._renderer = renderer

    def list_documents(self, subdir: str = "") -> dict[str, Any]:
        try:
            return {"root": str(self._paths.root), "documents": self._paths.list_documents(subdir)}
        except PathOutside as exc:
            return {"error": str(exc)}

    def inspect_document(self, path: str, include_empty: bool = False) -> dict[str, Any]:
        try:
            source = self._source(path)
            doc = inspect(source)
        except (PathOutside, UnsupportedFormat, FileNotFoundError, ValueError) as exc:
            return {"error": str(exc)}
        out = document_dict(doc, include_empty)
        out["path"] = path
        return out

    def plan_edit(self, path: str, replacements: list[dict[str, str]]) -> dict[str, Any]:
        try:
            source = self._source(path)
            plan = EditPlan(replacements=tuple(
                Replacement(target=str(r.get("target", "")), text=str(r.get("text", ""))) for r in replacements
            ))
            doc = inspect(source)
        except (PathOutside, UnsupportedFormat, FileNotFoundError, ValueError) as exc:
            return {"error": str(exc)}
        pv = preview(doc, plan)
        body = {
            "changes": [c.model_dump() for c in pv.changes], "issues": list(pv.issues), "ok": pv.ok,
        }
        pid = plan_id_for(path, source, plan)
        stored = self._plans.put(StoredPlan(plan_id=pid, rel_path=path, plan=plan, preview=body))
        return {"plan_id": stored.plan_id, "path": path, **stored.preview}

    def apply_edit(self, plan_id: str) -> dict[str, Any]:
        stored = self._plans.get(plan_id)
        if stored is None:
            return {"error": f"모르는 plan_id: {plan_id}. plan_edit 을 먼저 부른다"}
        if stored.result is not None:
            return stored.result
        if not stored.preview["ok"]:
            return {"error": "계획에 문제가 있어 적용하지 않는다", "issues": stored.preview["issues"]}
        try:
            source = self._source(stored.rel_path)
            if plan_id_for(stored.rel_path, source, stored.plan) != plan_id:
                return {"error": "계획을 세운 뒤 원본이 바뀌었다. plan_edit 을 다시 부른다"}
            before = inspect(source)
            out_path = self._paths.output_for(source, self._clock())
            after = apply(source, stored.plan, out_path)
        except (PathOutside, UnsupportedFormat, FileNotFoundError, ValueError, KeyError) as exc:
            return {"error": str(exc)}
        verified = verify_edit(before, after, stored.plan)
        stored.result = {
            "plan_id": plan_id, "source": stored.rel_path, "output": self._paths.relative(out_path),
            "verify": verified.model_dump(), "changes": stored.preview["changes"],
        }
        return stored.result

    def render_document(self, path: str, format: Literal["html", "pdf", "png"] = "pdf") -> dict[str, Any]:
        try:
            source = self._source(path)
            if format == "html":
                return {"path": path, "format": "html", "html": to_html(source)}
            files = render(source, format, self._paths.render_dir(source), renderer=self._renderer)
        except (PathOutside, UnsupportedFormat, FileNotFoundError, RenderUnavailable, ValueError) as exc:
            return {"error": str(exc)}
        return {"path": path, "format": format, "files": [self._paths.relative(f) for f in files]}

    def _source(self, rel: str) -> Path:
        source = self._paths.resolve(rel)
        if not source.is_file():
            raise FileNotFoundError(f"파일이 없다: {rel}")
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"파일이 너무 크다(20MB 초과): {rel}")
        return source


def build_server(service: DocsService) -> MCPServer:
    server = MCPServer(
        "docs",
        instructions="문서 폴더의 행정문서를 구조로 읽고, 편집 계획을 미리 본 뒤 승인된 계획만 새 파일로 저장한다.",
    )
    server.tool(
        name="list_documents", annotations=READ,
        description="문서 폴더의 파일 목록(DOCX, XLSX). subdir 로 하위 폴더만 볼 수 있다. 경로는 폴더 기준 상대 경로",
    )(service.list_documents)
    server.tool(
        name="inspect_document", annotations=READ,
        description=(
            "문서를 id 가 붙은 문단(p0, p1...)과 표 셀(t0r1c2) 목록으로 돌려준다. 편집 계획의 대상은 이 id 다"
        ),
    )(service.inspect_document)
    server.tool(
        name="plan_edit", annotations=READ,
        description=(
            "편집 계획(replacements: [{target: id, text: 새 글}])을 적용하지 않고 바뀔 곳(before, after)과"
            " 문제를 돌려준다. 돌아온 plan_id 를 사용자가 확인한 뒤 apply_edit 에 넘긴다"
        ),
    )(service.plan_edit)
    server.tool(
        name="apply_edit", annotations=WRITE,
        description=(
            "승인된 plan_id 를 적용해 원본 옆에 새 파일(.edited-<시각>)로 저장하고 검증 결과를 돌려준다."
            " 원본은 그대로다"
        ),
    )(service.apply_edit)
    server.tool(
        name="render_document", annotations=READ,
        description=(
            "문서를 html(본문 미리보기 문자열), pdf, png(쪽마다 파일)로 렌더한다. pdf 와 png 는 .render/ 아래 파일 경로"
        ),
    )(service.render_document)
    return server


def main() -> None:
    root = Path(os.environ.get("DOCS_ROOT", "/data/documents"))
    root.mkdir(parents=True, exist_ok=True)
    server = build_server(DocsService(DocsPaths(root)))
    server.run(
        "streamable-http", host=os.environ.get("DOCS_HOST", "0.0.0.0"), port=int(os.environ.get("DOCS_PORT", "8001")),
    )


if __name__ == "__main__":
    main()
